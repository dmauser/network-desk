# CI/CD Pipeline Design for Network Infrastructure

## Purpose

Design and implement CI/CD pipelines purpose-built for cloud network infrastructure deployments. Network changes are high-risk (one bad route can take down an entire environment), so pipelines must incorporate extensive validation, approval gates, and staged rollouts that general application pipelines don't require.

## Core Knowledge

### Pipeline Stage Architecture

The canonical network IaC pipeline follows this stage progression:

```
Lint → Validate → Plan → Security Scan → Approve → Apply → Test → Notify
```

Each stage serves a distinct purpose:

| Stage | Purpose | Failure Action |
|-------|---------|---------------|
| Lint | Syntax and formatting (terraform fmt, bicep lint) | Block PR merge |
| Validate | Schema and reference validation | Block PR merge |
| Plan | Preview changes, detect drift | Post to PR for review |
| Security Scan | Policy-as-code checks (Trivy config scanning, Checkov, OPA) | Block PR merge |
| Approve | Human gate for production changes | Wait or timeout |
| Apply | Execute infrastructure changes | Trigger rollback |
| Test | Post-deployment connectivity validation | Alert + potential rollback |
| Notify | Inform stakeholders of change status | Log only |

### GitHub Actions for Terraform Network Deployments

```yaml
name: Network Infrastructure CI/CD

on:
  pull_request:
    branches: [main]
    paths:
      - 'infrastructure/network/**'
      - '.github/workflows/network-*.yml'
  push:
    branches: [main]
    paths:
      - 'infrastructure/network/**'

permissions:
  id-token: write      # OIDC for Azure/AWS
  contents: read
  pull-requests: write  # Post plan comments

env:
  TF_VERSION: "<org-approved-current-terraform-version>"
  WORKING_DIR: "infrastructure/network"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Format Check
        run: terraform fmt -check -recursive
        working-directory: ${{ env.WORKING_DIR }}

      - name: TFLint
        uses: terraform-linters/setup-tflint@v4
      - run: |
          tflint --init
          tflint --recursive
        working-directory: ${{ env.WORKING_DIR }}

  validate:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Init
        run: terraform init -backend=false
        working-directory: ${{ env.WORKING_DIR }}

      - name: Terraform Validate
        run: terraform validate
        working-directory: ${{ env.WORKING_DIR }}

  security-scan:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Checkov Scan
        uses: bridgecrewio/checkov-action@v12
        with:
          directory: ${{ env.WORKING_DIR }}
          framework: terraform
          output_format: sarif
          soft_fail: false

      - name: Trivy Terraform config scan
        uses: aquasecurity/trivy-action@<pinned-full-length-commit-sha>
        with:
          scan-type: config
          scan-ref: ${{ env.WORKING_DIR }}
          format: sarif
          output: trivy-results.sarif
          severity: HIGH,CRITICAL
          exit-code: "1"

  plan:
    runs-on: ubuntu-latest
    needs: [validate, security-scan]
    environment: plan
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Azure Login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Terraform Init
        run: |
          terraform init \
            -backend-config="resource_group_name=${{ secrets.TF_STATE_RG }}" \
            -backend-config="storage_account_name=${{ secrets.TF_STATE_SA }}" \
            -backend-config="container_name=tfstate" \
            -backend-config="key=network.tfstate"
        working-directory: ${{ env.WORKING_DIR }}

      - name: Terraform Plan
        id: plan
        run: |
          terraform plan -no-color -out=tfplan \
            -var-file="environments/${{ github.base_ref || 'dev' }}.tfvars" \
            2>&1 | tee plan-output.txt
        working-directory: ${{ env.WORKING_DIR }}

      - name: Post Plan to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const plan = fs.readFileSync('${{ env.WORKING_DIR }}/plan-output.txt', 'utf8');
            const truncated = plan.length > 60000 ? plan.substring(0, 60000) + '\n... truncated' : plan;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Terraform Plan Output\n\`\`\`\n${truncated}\n\`\`\``
            });

      - name: Upload Plan Artifact
        uses: actions/upload-artifact@v4
        with:
          name: tfplan
          path: ${{ env.WORKING_DIR }}/tfplan

  apply:
    runs-on: ubuntu-latest
    needs: plan
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment:
      name: production
      url: https://portal.azure.com
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Azure Login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Download Plan
        uses: actions/download-artifact@v4
        with:
          name: tfplan
          path: ${{ env.WORKING_DIR }}

      - name: Terraform Init
        run: |
          terraform init \
            -backend-config="resource_group_name=${{ secrets.TF_STATE_RG }}" \
            -backend-config="storage_account_name=${{ secrets.TF_STATE_SA }}" \
            -backend-config="container_name=tfstate" \
            -backend-config="key=network.tfstate"
        working-directory: ${{ env.WORKING_DIR }}

      - name: Terraform Apply
        run: terraform apply -auto-approve tfplan
        working-directory: ${{ env.WORKING_DIR }}

  post-deploy-test:
    runs-on: ubuntu-latest
    needs: apply
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Network Connectivity Tests
        run: |
          chmod +x ./tests/network/smoke-tests.sh
          ./tests/network/smoke-tests.sh
```


### GitHub Actions Supply-Chain Hardening

For production network pipelines, pin third-party actions to full-length commit SHAs instead of mutable tags (for example, `actions/checkout@<full-length-sha>` after allowlisting the source repository). Restrict allowed actions at the organization/repository level to GitHub-owned actions plus explicitly approved vendors, and require CODEOWNERS review for `.github/workflows/**` changes. Review and refresh SHA pins on a scheduled cadence.

### GitHub Actions for Bicep Network Deployments

```yaml
name: Bicep Network Deployment

on:
  pull_request:
    paths: ['infra/network/**']
  push:
    branches: [main]
    paths: ['infra/network/**']

permissions:
  id-token: write
  contents: read
  pull-requests: write

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Bicep Lint
        run: az bicep lint --file infra/network/main.bicep

      - name: What-If (Plan)
        id: whatif
        run: |
          az deployment group what-if \
            --resource-group ${{ vars.NETWORK_RG }} \
            --template-file infra/network/main.bicep \
            --parameters infra/network/parameters.${{ github.base_ref || 'dev' }}.json \
            --no-pretty-print > whatif-output.txt 2>&1
        continue-on-error: true

      - name: Post What-If to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const output = fs.readFileSync('whatif-output.txt', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Bicep What-If Results\n\`\`\`\n${output}\n\`\`\``
            });

  deploy:
    runs-on: ubuntu-latest
    needs: validate
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy Network
        uses: azure/arm-deploy@v2
        with:
          resourceGroupName: ${{ vars.NETWORK_RG }}
          template: infra/network/main.bicep
          parameters: infra/network/parameters.prod.json
          failOnStdErr: false
```

### Azure DevOps Pipeline for Network IaC

```yaml
# azure-pipelines.yml
trigger:
  branches:
    include: [main]
  paths:
    include: ['infrastructure/network/*']

pr:
  branches:
    include: [main]
  paths:
    include: ['infrastructure/network/*']

variables:
  - group: network-secrets
  - name: tfVersion
    value: '<org-approved-current-terraform-version>'
  - name: workingDir
    value: 'infrastructure/network'

stages:
  - stage: Validate
    jobs:
      - job: LintAndValidate
        pool:
          vmImage: 'ubuntu-latest'
        steps:
          - task: TerraformInstaller@1
            inputs:
              terraformVersion: $(tfVersion)

          - script: terraform fmt -check -recursive
            displayName: 'Format Check'
            workingDirectory: $(workingDir)

          - script: |
              terraform init -backend=false
              terraform validate
            displayName: 'Validate'
            workingDirectory: $(workingDir)

          - script: |
              pip install checkov
              checkov -d $(workingDir) --framework terraform
            displayName: 'Security Scan'

  - stage: Plan
    dependsOn: Validate
    jobs:
      - job: TerraformPlan
        pool:
          vmImage: 'ubuntu-latest'
        steps:
          - task: TerraformInstaller@1
            inputs:
              terraformVersion: $(tfVersion)

          - task: AzureCLI@2
            displayName: 'Terraform Plan'
            inputs:
              azureSubscription: 'network-service-connection'
              scriptType: bash
              scriptLocation: inlineScript
              inlineScript: |
                export ARM_CLIENT_ID=$servicePrincipalId
                export ARM_CLIENT_SECRET=$servicePrincipalKey
                export ARM_TENANT_ID=$tenantId
                export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
                
                cd $(workingDir)
                terraform init
                terraform plan -out=tfplan -var-file="environments/$(Build.SourceBranchName).tfvars"
              addSpnToEnvironment: true

          - publish: $(workingDir)/tfplan
            artifact: tfplan

  - stage: Apply
    dependsOn: Plan
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: TerraformApply
        pool:
          vmImage: 'ubuntu-latest'
        environment: 'network-production'  # Requires approval
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self

                - task: TerraformInstaller@1
                  inputs:
                    terraformVersion: $(tfVersion)

                - download: current
                  artifact: tfplan

                - task: AzureCLI@2
                  displayName: 'Terraform Apply'
                  inputs:
                    azureSubscription: 'network-service-connection'
                    scriptType: bash
                    scriptLocation: inlineScript
                    inlineScript: |
                      export ARM_CLIENT_ID=$servicePrincipalId
                      export ARM_CLIENT_SECRET=$servicePrincipalKey
                      export ARM_TENANT_ID=$tenantId
                      export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
                      
                      cd $(workingDir)
                      terraform init
                      terraform apply -auto-approve $(Pipeline.Workspace)/tfplan/tfplan
                    addSpnToEnvironment: true
```

### Environment Promotion Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    Branch Strategy                            │
├─────────────────────────────────────────────────────────────┤
│  feature/* ──PR──► dev ──PR──► staging ──PR──► main (prod)  │
│      │              │              │               │          │
│   Validate       Deploy to      Deploy to      Deploy to     │
│   + Plan         Dev Env        Staging        Production    │
│                  (auto)         (auto)         (manual gate) │
└─────────────────────────────────────────────────────────────┘
```

Terraform workspace structure for environment promotion:

```hcl
# environments/dev.tfvars
environment    = "dev"
address_space  = ["10.1.0.0/16"]
vnet_name      = "vnet-network-dev"
enable_firewall = false
sku_tier       = "Basic"

# environments/staging.tfvars
environment    = "staging"
address_space  = ["10.2.0.0/16"]
vnet_name      = "vnet-network-staging"
enable_firewall = true
sku_tier       = "Standard"

# environments/prod.tfvars
environment    = "prod"
address_space  = ["10.0.0.0/16"]
vnet_name      = "vnet-network-prod"
enable_firewall = true
sku_tier       = "Premium"
```

### Secrets Management in Pipelines

#### GitHub Actions with Azure Key Vault

```yaml
- name: Get Secrets from Key Vault
  uses: azure/get-keyvault-secrets@v1
  with:
    keyvault: "kv-network-automation"
    secrets: "tf-state-access-key, vpn-shared-key, er-service-key"
  id: kv-secrets

- name: Terraform Apply
  env:
    ARM_ACCESS_KEY: ${{ steps.kv-secrets.outputs.tf-state-access-key }}
    TF_VAR_vpn_shared_key: ${{ steps.kv-secrets.outputs.vpn-shared-key }}
  run: terraform apply -auto-approve tfplan
```

#### OIDC Federation (Preferred — No Stored Secrets)

```yaml
# GitHub Actions OIDC — no client secret needed
- uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

```hcl
# Terraform OIDC provider config
provider "azurerm" {
  features {}
  use_oidc = true
}
```

### Parallel vs Sequential Deployments

Network resources often have dependencies that prevent full parallelization:

```yaml
# Dependency-aware deployment order
jobs:
  deploy-hub-vnet:
    # No dependencies — deploys first
    runs-on: ubuntu-latest
    steps: [...]

  deploy-firewall:
    needs: deploy-hub-vnet  # Firewall needs the hub VNet
    runs-on: ubuntu-latest
    steps: [...]

  deploy-spoke-vnets:
    needs: deploy-hub-vnet  # Spokes peer to hub
    strategy:
      matrix:
        spoke: [spoke-app, spoke-data, spoke-mgmt]
      max-parallel: 2  # Limit concurrent peerings
    runs-on: ubuntu-latest
    steps: [...]

  deploy-route-tables:
    needs: [deploy-firewall, deploy-spoke-vnets]
    runs-on: ubuntu-latest
    steps: [...]
```

### Terraform Cloud / Spacelift Integration

```hcl
# Terraform Cloud workspace config
terraform {
  cloud {
    organization = "my-org"
    workspaces {
      tags = ["network", "azure"]
    }
  }
}
```

```yaml
# Spacelift stack configuration (.spacelift/config.yml)
version: "1"
stacks:
  network-hub:
    path: infrastructure/network/hub
    terraform_version: "<org-approved-current-terraform-version>"
    autodeploy: false
    before_apply:
      - checkov -d . --framework terraform
    policies:
      - network-change-policy

  network-spokes:
    path: infrastructure/network/spokes
    terraform_version: "<org-approved-current-terraform-version>"
    autodeploy: false
    depends_on:
      - network-hub
```

## Best Practices

1. **Pin tool versions** — Pin Terraform/providers to org-approved current versions and pin GitHub Actions to full-length SHAs from allowlisted sources
2. **Use saved plans** — Generate plan in one job, apply that exact plan in another (never plan-and-apply in one step for production)
3. **OIDC over secrets** — Prefer workload identity federation; eliminate long-lived credentials
4. **Limit blast radius** — Split network into logical stacks (hub, spokes, DNS, firewall) with separate state files
5. **PR-based workflow** — All changes via PR; no direct pushes to main for network infra
6. **Mandatory reviews** — Require 2+ reviewers for production network changes (CODEOWNERS)
7. **Time-limited approvals** — Auto-expire pending deployments after 4 hours
8. **Artifact-based deploys** — Upload plan artifacts; never re-plan during apply
9. **Concurrency controls** — Use `concurrency` groups to prevent parallel applies to the same environment
10. **Notification integration** — Post deployment status to Slack/Teams for visibility

---

**Analysis only — verify against vendor documentation before applying.**
