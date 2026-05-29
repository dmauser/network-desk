# Configuration Drift Detection

## Purpose

Detect and manage configuration drift in cloud network infrastructure — the divergence between the desired state (defined in IaC) and the actual state (what's deployed). Network drift is particularly dangerous because unauthorized route changes, NSG modifications, or peering alterations can silently break connectivity or create security holes.

## Core Knowledge

### What Causes Network Drift

| Source | Example | Risk Level |
|--------|---------|------------|
| Portal changes | Engineer adds NSG rule via Azure Portal | High |
| CLI/SDK scripts | Ops team runs `az network` command directly | High |
| Auto-scaling | Cloud provider modifies LB backend pools | Low |
| Provider updates | Azure adds default rules to new NSGs | Medium |
| Disaster recovery | Failover changes routing tables | Medium |
| Third-party tools | Monitoring agent modifies security groups | Medium |

### Terraform State Drift Detection in CI

#### Scheduled Drift Detection Workflow (GitHub Actions)

```yaml
name: Network Drift Detection

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch: {}

permissions:
  id-token: write
  contents: read
  issues: write

env:
  TF_VERSION: "1.7.0"
  WORKING_DIR: "infrastructure/network"

jobs:
  detect-drift:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        stack: [hub, spokes, firewall, dns]
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Terraform Init
        working-directory: ${{ env.WORKING_DIR }}/${{ matrix.stack }}
        run: terraform init

      - name: Detect Drift
        id: drift
        working-directory: ${{ env.WORKING_DIR }}/${{ matrix.stack }}
        run: |
          terraform plan -detailed-exitcode -no-color \
            -var-file="environments/prod.tfvars" \
            -out=drift-plan.tfplan 2>&1 | tee drift-output.txt
          
          EXIT_CODE=$?
          if [ $EXIT_CODE -eq 2 ]; then
            echo "drift_detected=true" >> $GITHUB_OUTPUT
            echo "## ⚠️ Drift Detected in ${{ matrix.stack }}" >> $GITHUB_STEP_SUMMARY
            cat drift-output.txt >> $GITHUB_STEP_SUMMARY
          elif [ $EXIT_CODE -eq 0 ]; then
            echo "drift_detected=false" >> $GITHUB_OUTPUT
            echo "## ✅ No Drift in ${{ matrix.stack }}" >> $GITHUB_STEP_SUMMARY
          else
            echo "drift_detected=error" >> $GITHUB_OUTPUT
            exit 1
          fi
        continue-on-error: true

      - name: Create Issue on Drift
        if: steps.drift.outputs.drift_detected == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const drift = fs.readFileSync(
              '${{ env.WORKING_DIR }}/${{ matrix.stack }}/drift-output.txt', 'utf8'
            );
            const truncated = drift.length > 60000
              ? drift.substring(0, 60000) + '\n... truncated'
              : drift;
            
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `🔄 Network Drift Detected: ${{ matrix.stack }}`,
              body: `## Drift detected in \`${{ matrix.stack }}\` stack\n\n` +
                    `**Detected at:** ${new Date().toISOString()}\n\n` +
                    `\`\`\`\n${truncated}\n\`\`\`\n\n` +
                    `### Action Required\n` +
                    `1. Review the changes above\n` +
                    `2. If intentional: update IaC to match\n` +
                    `3. If unauthorized: revert via \`terraform apply\`\n`,
              labels: ['drift', 'network', 'automated']
            });

      - name: Send Alert
        if: steps.drift.outputs.drift_detected == 'true'
        run: |
          curl -X POST "${{ secrets.TEAMS_WEBHOOK_URL }}" \
            -H "Content-Type: application/json" \
            -d '{
              "title": "⚠️ Network Drift: ${{ matrix.stack }}",
              "text": "Configuration drift detected in the ${{ matrix.stack }} network stack. Review the GitHub Issue for details."
            }'
```

### Azure Resource Graph for Out-of-Band Change Detection

```kusto
// Find network resources modified outside of Terraform
// (resources with tags missing "managed-by: terraform")
Resources
| where type startswith "microsoft.network"
| where tags !has "managed-by" or tags["managed-by"] != "terraform"
| where properties.provisioningState == "Succeeded"
| project name, type, resourceGroup, subscriptionId,
          changedTime=properties.changedTime
| order by changedTime desc
```

```kusto
// Detect NSG rules added in the last 24 hours
ResourceChanges
| where resourceType == "microsoft.network/networksecuritygroups"
| where changeType == "Update"
| where properties.changes has "securityRules"
| where todatetime(properties.changeAttributes.timestamp) > ago(24h)
| project resourceId, changeType,
          timestamp=properties.changeAttributes.timestamp,
          changedBy=properties.changeAttributes.changedBy
| order by timestamp desc
```

```yaml
# GitHub Actions job using Resource Graph
- name: Check for Unmanaged Changes
  run: |
    UNMANAGED=$(az graph query -q "
      Resources
      | where type startswith 'microsoft.network'
      | where tags['managed-by'] != 'terraform'
      | where todatetime(properties.changedTime) > ago(6h)
      | count
    " --query "data[0].Count" -o tsv)
    
    if [ "$UNMANAGED" -gt 0 ]; then
      echo "::warning::Found $UNMANAGED unmanaged network changes in the last 6 hours"
    fi
```

### AWS Config Rules for Network Compliance

```hcl
# AWS Config rule: detect security groups with 0.0.0.0/0 ingress
resource "aws_config_config_rule" "no_unrestricted_sg" {
  name = "restricted-security-groups"

  source {
    owner             = "AWS"
    source_identifier = "INCOMING_SSH_DISABLED"
  }

  scope {
    compliance_resource_types = ["AWS::EC2::SecurityGroup"]
  }
}

# Custom Config rule for VPC flow logs enabled
resource "aws_config_config_rule" "vpc_flow_logs" {
  name = "vpc-flow-logs-enabled"

  source {
    owner             = "AWS"
    source_identifier = "VPC_FLOW_LOGS_ENABLED"
  }

  scope {
    compliance_resource_types = ["AWS::EC2::VPC"]
  }
}

# Detect route table changes
resource "aws_config_config_rule" "no_unrestricted_route" {
  name = "detect-route-changes"

  source {
    owner = "CUSTOM_LAMBDA"
    source_identifier = aws_lambda_function.route_checker.arn

    source_detail {
      event_source = "aws.config"
      message_type = "ConfigurationItemChangeNotification"
    }
  }

  scope {
    compliance_resource_types = ["AWS::EC2::RouteTable"]
  }
}
```

```python
# Lambda function for custom AWS Config rule
import json
import boto3

config_client = boto3.client('config')

def lambda_handler(event, context):
    """Check if route table has unauthorized routes."""
    invoking_event = json.loads(event['invokingEvent'])
    configuration_item = invoking_event['configurationItem']
    
    routes = configuration_item['configuration'].get('routes', [])
    
    # Check for routes not managed by our IaC
    unauthorized = []
    for route in routes:
        # Routes managed by IaC have a specific tag pattern
        if route.get('origin') == 'CreateRoute':
            # Check if this route is in our known-good list
            if not is_known_route(route, configuration_item['resourceId']):
                unauthorized.append(route)
    
    compliance = 'COMPLIANT' if not unauthorized else 'NON_COMPLIANT'
    annotation = f"Found {len(unauthorized)} unauthorized routes" if unauthorized else ""
    
    config_client.put_evaluations(
        Evaluations=[{
            'ComplianceResourceType': configuration_item['resourceType'],
            'ComplianceResourceId': configuration_item['resourceId'],
            'ComplianceType': compliance,
            'Annotation': annotation,
            'OrderingTimestamp': configuration_item['configurationItemCaptureTime']
        }],
        ResultToken=event['resultToken']
    )
```

### State File Management and Locking

#### Azure Backend with Locking

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate"
    container_name       = "network-state"
    key                  = "hub-network.tfstate"
    
    # Enable state locking via Azure Blob lease
    use_azuread_auth = true
  }
}
```

#### S3 Backend with Native Lockfile Locking

```hcl
terraform {
  backend "s3" {
    bucket         = "my-org-terraform-state"
    key            = "network/vpc-hub.tfstate"
    region         = "us-east-1"
    encrypt        = true
    use_lockfile    = true
    
    # Use assume role for cross-account state access
    role_arn = "arn:aws:iam::123456789012:role/TerraformStateAccess"
  }
}
```

DynamoDB locking is legacy for the S3 backend; retain it only for older estates that have not migrated to native lock files.

#### State Backup Before Operations

```yaml
- name: Backup State Before Apply
  run: |
    terraform state pull > state-backup-$(date +%Y%m%d-%H%M%S).json
    az storage blob upload \
      --account-name ${{ secrets.STATE_BACKUP_SA }} \
      --container-name state-backups \
      --file state-backup-*.json \
      --name "network/$(date +%Y%m%d-%H%M%S).json"
```

### Remediation Strategies

#### Auto-Remediation (Non-Production)

```yaml
# Auto-fix drift in dev/staging environments
- name: Auto-Remediate Drift
  if: steps.drift.outputs.drift_detected == 'true' && env.ENVIRONMENT != 'prod'
  run: |
    terraform apply -auto-approve \
      -var-file="environments/${{ env.ENVIRONMENT }}.tfvars"
    echo "::notice::Auto-remediated drift in ${{ env.ENVIRONMENT }}"
```

#### Alert-Only (Production)

```yaml
# Production: alert only, require manual intervention
- name: Alert on Production Drift
  if: steps.drift.outputs.drift_detected == 'true' && env.ENVIRONMENT == 'prod'
  run: |
    echo "::error::Production drift detected — manual review required"
    # Create PagerDuty incident
    curl -X POST "https://events.pagerduty.com/v2/enqueue" \
      -H "Content-Type: application/json" \
      -d '{
        "routing_key": "${{ secrets.PD_ROUTING_KEY }}",
        "event_action": "trigger",
        "payload": {
          "summary": "Network drift detected in production",
          "severity": "warning",
          "source": "terraform-drift-detection"
        }
      }'
```

#### Selective Import (Adopt Out-of-Band Changes)

```bash
#!/bin/bash
# When a portal change was intentional, import it into state
# Then update the IaC code to match

# Example: NSG rule added via portal
terraform import \
  'azurerm_network_security_rule.allow_monitoring' \
  '/subscriptions/.../networkSecurityGroups/nsg-app/securityRules/AllowMonitoring'

# Then add matching code:
# resource "azurerm_network_security_rule" "allow_monitoring" { ... }
```

### Drift Detection Dashboard

```kusto
// Azure Monitor workbook query — drift events over time
customEvents
| where name == "TerraformDriftDetected"
| extend stack = tostring(customDimensions.stack),
         resourceCount = toint(customDimensions.driftedResources)
| summarize DriftEvents=count(), ResourcesAffected=sum(resourceCount)
    by bin(timestamp, 1d), stack
| render timechart
```

## Best Practices

1. **Run drift detection frequently** — Every 4-6 hours for production; once daily for non-prod
2. **Tag everything** — Use `managed-by: terraform` tags to distinguish IaC-managed resources
3. **Separate detection from remediation** — Always detect first; only auto-fix in non-prod
4. **State file backups** — Back up state before every apply; retain for 30+ days
5. **Locking is mandatory** — Never run Terraform without state locking in shared environments
6. **Audit trail** — Log who/what triggered every drift detection and remediation
7. **Ignore known noise** — Use `lifecycle { ignore_changes }` for fields that legitimately change (e.g., `last_modified_time`)
8. **Correlate with change log** — Cross-reference drift with Azure Activity Log / CloudTrail to find the actor
9. **Escalation path** — Drift in production should page on-call; drift in dev can be a Slack notification
10. **Prevent drift at the source** — Use Azure Policy deny effects or AWS SCPs to block portal changes to IaC-managed resources

---

**Analysis only — verify against vendor documentation before applying.**
