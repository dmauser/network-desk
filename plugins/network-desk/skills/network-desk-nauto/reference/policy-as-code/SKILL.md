# Policy-as-Code for Network Infrastructure

## Purpose

Enforce network security and compliance policies programmatically — before deployment (shift-left) and at runtime (continuous compliance). Policy-as-code eliminates human error in reviews, ensures consistency across environments, and provides audit evidence for compliance frameworks.

## Core Knowledge

### Policy Enforcement Points

```
┌──────────────────────────────────────────────────────────────────┐
│                    Policy Enforcement Layers                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  IDE / Pre-commit ──► CI Pipeline ──► Deployment ──► Runtime      │
│       │                    │               │             │         │
│    Trivy/Checkov      Checkov/OPA      ARM/Terraform   Azure      │
│    Bicep linter       Trivy config     deny effects    Policy     │
│                       Terrascan                        AWS Config │
│                       Sentinel                         SCPs       │
│                                                                    │
│  ◄─── Shift Left (cheaper to fix) ──── Shift Right (last resort)─►│
└──────────────────────────────────────────────────────────────────┘
```

### Azure Policy for Network Resources

#### Built-in Network Policies

| Policy | Effect | Description |
|--------|--------|-------------|
| `Deny-PublicIP` | Deny | Prevent public IP creation |
| `Deploy-NSG-FlowLogs` | DeployIfNotExists | Auto-enable NSG flow logs |
| `Deny-Subnet-Without-NSG` | Deny | Require NSG on every subnet |
| `Audit-VNet-Peering` | Audit | Flag cross-subscription peering |
| `Deny-RDP-From-Internet` | Deny | Block inbound RDP from 0.0.0.0/0 |

#### Custom Azure Policy: Enforce Private Endpoints

```json
{
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        {
          "field": "type",
          "equals": "Microsoft.Storage/storageAccounts"
        },
        {
          "field": "Microsoft.Storage/storageAccounts/publicNetworkAccess",
          "notEquals": "Disabled"
        }
      ]
    },
    "then": {
      "effect": "deny"
    }
  },
  "parameters": {}
}
```

#### Custom Azure Policy: Require Specific Subnets Have UDRs

```json
{
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        {
          "field": "type",
          "equals": "Microsoft.Network/virtualNetworks/subnets"
        },
        {
          "field": "name",
          "notIn": ["AzureFirewallSubnet", "GatewaySubnet", "AzureBastionSubnet"]
        },
        {
          "field": "Microsoft.Network/virtualNetworks/subnets/routeTable.id",
          "exists": "false"
        }
      ]
    },
    "then": {
      "effect": "deny"
    }
  }
}
```

#### Deploying Azure Policy via Terraform

```hcl
resource "azurerm_policy_definition" "deny_public_ip" {
  name         = "deny-public-ip-creation"
  policy_type  = "Custom"
  mode         = "All"
  display_name = "Deny Public IP Creation"
  description  = "Prevents creation of public IP addresses in network resource groups"

  metadata = jsonencode({
    category = "Network"
    version  = "1.0.0"
  })

  policy_rule = jsonencode({
    if = {
      allOf = [
        { field = "type", equals = "Microsoft.Network/publicIPAddresses" },
        { field = "location", in = ["eastus", "westus2", "westeurope"] }
      ]
    }
    then = { effect = "[parameters('effect')]" }
  })

  parameters = jsonencode({
    effect = {
      type          = "String"
      defaultValue  = "Deny"
      allowedValues = ["Audit", "Deny", "Disabled"]
    }
  })
}

resource "azurerm_management_group_policy_assignment" "deny_public_ip" {
  name                 = "deny-public-ip"
  policy_definition_id = azurerm_policy_definition.deny_public_ip.id
  management_group_id  = data.azurerm_management_group.network.id

  parameters = jsonencode({
    effect = { value = "Deny" }
  })
}
```

### AWS Service Control Policies + Config Rules

#### SCP: Deny Internet Gateway Creation in Production

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyIGWInProduction",
      "Effect": "Deny",
      "Action": [
        "ec2:CreateInternetGateway",
        "ec2:AttachInternetGateway"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": ["us-east-1", "us-west-2"],
          "aws:PrincipalTag/environment": "production"
        }
      }
    }
  ]
}
```

Do not use unsupported EC2 condition keys such as `ec2:RouteTableId` or `ec2:DestinationCidr` to deny `ec2:CreateRoute`; AWS will not enforce that intent. For default-route control, use detective/remediation controls such as AWS Config custom rules or EventBridge on CloudTrail `CreateRoute` events, then validate route table tags/owners and delete or quarantine unauthorized `0.0.0.0/0` routes.

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventSource": ["ec2.amazonaws.com"],
    "eventName": ["CreateRoute"],
    "requestParameters": {
      "destinationCidrBlock": ["0.0.0.0/0"]
    }
  }
}
```

#### AWS Config Rule: Require VPC Flow Logs (Terraform)

```hcl
resource "aws_config_config_rule" "vpc_flow_logs_enabled" {
  name = "vpc-flow-logs-enabled"

  source {
    owner             = "AWS"
    source_identifier = "VPC_FLOW_LOGS_ENABLED"
  }

  input_parameters = jsonencode({
    trafficType = "ALL"
  })

  scope {
    compliance_resource_types = ["AWS::EC2::VPC"]
  }
}

resource "aws_config_config_rule" "restricted_ssh" {
  name = "incoming-ssh-disabled"

  source {
    owner             = "AWS"
    source_identifier = "INCOMING_SSH_DISABLED"
  }

  scope {
    compliance_resource_types = ["AWS::EC2::SecurityGroup"]
  }
}
```

### Open Policy Agent (OPA) / Rego for Terraform

#### Rego Policy: No Public IPs in Network Module

```rego
# policy/network/no_public_ips.rego
package terraform.network

import input.plan as tfplan

# Deny any public IP resource creation
deny[msg] {
    resource := tfplan.resource_changes[_]
    resource.type == "azurerm_public_ip"
    resource.change.actions[_] == "create"
    msg := sprintf("Public IP creation denied: %s. Use Private Endpoints or NAT Gateway instead.", [resource.address])
}

# Deny NSG rules allowing inbound from 0.0.0.0/0
deny[msg] {
    resource := tfplan.resource_changes[_]
    resource.type == "azurerm_network_security_rule"
    resource.change.actions[_] == "create"
    resource.change.after.direction == "Inbound"
    resource.change.after.source_address_prefix == "*"
    resource.change.after.access == "Allow"
    msg := sprintf("NSG rule %s allows unrestricted inbound access. Specify source CIDR.", [resource.address])
}

# Require encryption on VPN connections
deny[msg] {
    resource := tfplan.resource_changes[_]
    resource.type == "azurerm_virtual_network_gateway_connection"
    resource.change.actions[_] == "create"
    not resource.change.after.ipsec_policy
    msg := sprintf("VPN connection %s must define explicit IPsec policy with IKEv2.", [resource.address])
}
```

#### Rego Policy: Enforce Subnet Sizing

```rego
# policy/network/subnet_sizing.rego
package terraform.network

import input.plan as tfplan

# Minimum subnet size /28 (16 IPs)
deny[msg] {
    resource := tfplan.resource_changes[_]
    resource.type == "azurerm_subnet"
    resource.change.actions[_] == "create"
    prefix := resource.change.after.address_prefixes[0]
    cidr_size := to_number(split(prefix, "/")[1])
    cidr_size > 28
    msg := sprintf("Subnet %s has prefix /%d — minimum size is /28 for Azure reserved addresses.", [resource.address, cidr_size])
}

# Maximum VNet size /16 (prevent accidental large allocations)
deny[msg] {
    resource := tfplan.resource_changes[_]
    resource.type == "azurerm_virtual_network"
    resource.change.actions[_] == "create"
    prefix := resource.change.after.address_space[0]
    cidr_size := to_number(split(prefix, "/")[1])
    cidr_size < 16
    msg := sprintf("VNet %s has address space /%d — maximum allowed is /16.", [resource.address, cidr_size])
}
```

#### Running OPA in CI Pipeline

```yaml
- name: OPA Policy Check
  run: |
    # Generate plan JSON
    terraform plan -out=tfplan.binary
    terraform show -json tfplan.binary > tfplan.json
    
    # Evaluate policies
    opa eval \
      --data policy/ \
      --input tfplan.json \
      "data.terraform.network.deny" \
      --format pretty > policy-results.txt
    
    # Fail if any denies
    VIOLATIONS=$(opa eval \
      --data policy/ \
      --input tfplan.json \
      "count(data.terraform.network.deny)" \
      --format raw)
    
    if [ "$VIOLATIONS" -gt 0 ]; then
      echo "::error::$VIOLATIONS policy violations found"
      cat policy-results.txt
      exit 1
    fi
```

### Pre-Deployment Scanners

#### Checkov Configuration

```yaml
# .checkov.yml
framework:
  - terraform
check:
  - CKV_AZURE_9    # Ensure NSG does not allow SSH from internet
  - CKV_AZURE_10   # Ensure NSG does not allow RDP from internet
  - CKV_AZURE_12   # Ensure network watcher flow log retention > 90 days
  - CKV_AZURE_77   # Ensure VNet has DDoS protection
  - CKV_AZURE_160  # Ensure private endpoints used for supported services
  - CKV_AWS_23     # Ensure every SG rule has a description
  - CKV_AWS_24     # Ensure no SG allows 0.0.0.0/0 to port 22
  - CKV_AWS_260    # Ensure no SG allows 0.0.0.0/0 to port 3389
skip_check:
  - CKV_AZURE_4    # Skip: managed by separate firewall policy
soft_fail_on:
  - CKV_AZURE_77   # DDoS protection is expensive for dev
```

```yaml
# CI integration
- name: Checkov Network Scan
  uses: bridgecrewio/checkov-action@v12
  with:
    directory: infrastructure/network
    framework: terraform
    check: CKV_AZURE_9,CKV_AZURE_10,CKV_AZURE_12,CKV_AZURE_160
    output_format: cli,sarif
    output_file_path: console,results.sarif
    soft_fail: false
```

#### Trivy Config Scanning with Custom Rego

Use Trivy config scanning for Terraform misconfiguration checks. tfsec custom rules are legacy; migrate custom checks to Rego policies that can run with Trivy or OPA.

```yaml
# trivy.yaml
scan:
  scanners:
    - misconfig
misconfiguration:
  terraform:
    exclude-downloaded-modules: false
  policy:
    - policy/trivy
severity:
  - HIGH
  - CRITICAL
```

```rego
# policy/trivy/azure_network.rego
package user.azure.network

deny[res] {
  input.resource_type == "azurerm_virtual_network_peering"
  input.config.allow_forwarded_traffic.value == true
  res := {
    "msg": sprintf("VNet peering %s allows forwarded traffic; require explicit approval.", [input.__defsec_metadata.resource]),
    "severity": "HIGH"
  }
}

deny[res] {
  input.resource_type == "azurerm_subnet"
  not input.config.service_endpoints
  res := {
    "msg": sprintf("Subnet %s is missing required service endpoint review.", [input.__defsec_metadata.resource]),
    "severity": "MEDIUM"
  }
}
```

```yaml
# CI integration
- name: Trivy Terraform config scan
  uses: aquasecurity/trivy-action@<pinned-full-length-commit-sha>
  with:
    scan-type: config
    scan-ref: infrastructure/network
    trivy-config: trivy.yaml
    exit-code: "1"
```

#### Terrascan

```yaml
# CI step for Terrascan
- name: Terrascan Network Scan
  run: |
    terrascan scan \
      -i terraform \
      -d infrastructure/network \
      -p policy/terrascan/ \
      --severity high \
      -o json > terrascan-results.json
    
    HIGH_COUNT=$(jq '.results.violations | map(select(.severity == "HIGH")) | length' terrascan-results.json)
    if [ "$HIGH_COUNT" -gt 0 ]; then
      echo "::error::$HIGH_COUNT high-severity violations found"
      jq '.results.violations[] | select(.severity == "HIGH") | .description' terrascan-results.json
      exit 1
    fi
```

### Common Network Policies

| Policy | Enforcement | Implementation |
|--------|-------------|----------------|
| No public IPs | Deny on create | Azure Policy / SCP / OPA |
| NSG on all subnets | Deny subnet without NSG | Azure Policy |
| Flow logs enabled | DeployIfNotExists | Azure Policy / Config Rule |
| No 0.0.0.0/0 ingress | Deny NSG rule | OPA + Azure Policy |
| Require encryption | Deny unencrypted VPN | OPA / Trivy config scanning |
| Private endpoints only | Deny public access on PaaS | Azure Policy |
| Approved regions only | Deny outside allowed regions | Azure Policy / SCP |
| Tag compliance | Deny untagged network resources | Azure Policy / SCP |
| Max subnet size | Deny oversized subnets | OPA |
| DNS zone restrictions | Audit private DNS zone links | Azure Policy |

### Policy Testing and Development

#### Unit Testing OPA Policies

```rego
# policy/network/no_public_ips_test.rego
package terraform.network

# Test: should deny public IP creation
test_deny_public_ip {
    deny["Public IP creation denied: azurerm_public_ip.bad. Use Private Endpoints or NAT Gateway instead."] with input.plan as {
        "resource_changes": [{
            "type": "azurerm_public_ip",
            "address": "azurerm_public_ip.bad",
            "change": {"actions": ["create"]}
        }]
    }
}

# Test: should allow private resources
test_allow_private_endpoint {
    count(deny) == 0 with input.plan as {
        "resource_changes": [{
            "type": "azurerm_private_endpoint",
            "address": "azurerm_private_endpoint.good",
            "change": {"actions": ["create"]}
        }]
    }
}
```

```bash
# Run OPA tests
opa test policy/ -v
```

#### Testing Azure Policy with Bicep What-If

```bash
# Test policy effect before assignment
az policy definition create \
  --name "test-deny-public-ip" \
  --rules policy-rules.json \
  --mode All

# Simulate with a what-if deployment
az deployment group what-if \
  --resource-group rg-policy-test \
  --template-file test-public-ip.bicep
# Expected: "Resource will be denied by policy"
```

## Best Practices

1. **Layer defenses** — Use OPA in CI (shift-left) AND Azure Policy at runtime (defense-in-depth)
2. **Start with Audit** — Deploy policies in Audit mode first; switch to Deny after baselining
3. **Exemption process** — Define a formal process for policy exemptions with expiration dates
4. **Version policies** — Store policies in Git; version with semver; test before promotion
5. **Test with real plans** — Unit test policies against realistic `terraform plan` JSON output
6. **Document policy rationale** — Every deny rule needs a "why" and a "how to comply" message
7. **Monitor compliance** — Dashboard showing compliance % over time; alert on regressions
8. **Policy-as-code review** — Require PR reviews for policy changes just like infrastructure code
9. **Gradual rollout** — New policies: Disabled → Audit → Deny (with 2-week soak at each stage)
10. **Exception tracking** — All exemptions tracked in a register with owner, reason, and review date

---

**Analysis only — verify against vendor documentation before applying.**
