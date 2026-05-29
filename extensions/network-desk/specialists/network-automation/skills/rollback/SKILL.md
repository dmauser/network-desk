# Rollback and Change Management

## Purpose

Provide strategies for safely rolling back network infrastructure changes when deployments fail or cause unintended impact. Network rollback is uniquely challenging because changes are often stateful (routes propagate, peerings establish, DNS caches), and a failed rollback can be worse than the original failure.

## Core Knowledge

### Change Risk Assessment Matrix

| Change Type | Risk Level | Rollback Complexity | Strategy |
|-------------|-----------|--------------------|-----------| 
| NSG rule add | Low | Simple | Terraform revert |
| VNet peering | Medium | Moderate | Staged + validation |
| Route table change | High | Complex | Blue-green |
| VPN gateway config | High | Complex | Maintenance window |
| DNS zone change | High | TTL-dependent | Canary + low TTL |
| Firewall policy | Critical | Complex | Canary regions |
| Address space change | Critical | Destructive | Blue-green mandatory |

### Terraform State Rollback Strategies

#### Strategy 1: Revert via Git (Preferred)

```bash
# The safest rollback: revert the code and re-apply
git revert HEAD --no-edit
git push origin main
# Pipeline will: plan → approve → apply the reverted state
```

This works because:
- Terraform is declarative — reverting code reverts desired state
- The pipeline runs the same validation/testing gates
- Full audit trail in Git history

#### Strategy 2: State Manipulation (Emergency Only)

```bash
# ⚠️ EMERGENCY ONLY — bypass normal pipeline
# Use when the pipeline itself is broken

# 1. Pull current state
terraform state pull > current-state.json

# 2. Backup
cp current-state.json state-backup-$(date +%s).json

# 3. Remove problematic resource from state (won't delete the resource)
terraform state rm 'azurerm_route_table.broken'

# 4. Import the previous known-good resource
terraform import 'azurerm_route_table.good' /subscriptions/.../routeTables/rt-good

# 5. Apply to reconcile
terraform apply -target='azurerm_route_table.good'
```

#### Strategy 3: Targeted Destroy and Recreate

```bash
# When a specific resource is misconfigured
terraform apply -replace='azurerm_network_security_rule.broken_rule'

# Or destroy just the broken resource
terraform destroy -target='azurerm_virtual_network_peering.bad'
terraform apply  # Recreates with correct config
```

### Blue-Green Network Deployments

#### Concept

Maintain two parallel network environments; switch traffic between them:

```
┌─────────────────────────────────────────────────────────┐
│                    Traffic Manager / DNS                  │
│                         │                                │
│              ┌──────────┴──────────┐                     │
│              │                     │                     │
│         ┌────▼────┐          ┌────▼────┐                │
│         │  BLUE   │          │  GREEN  │                │
│         │ (Live)  │          │ (Staged)│                │
│         │         │          │         │                │
│         │ Hub VNet│          │ Hub VNet│                │
│         │ Spokes  │          │ Spokes  │                │
│         │ FW/GW   │          │ FW/GW   │                │
│         └─────────┘          └─────────┘                │
└─────────────────────────────────────────────────────────┘
```

#### Implementation with Terraform Workspaces

```hcl
# main.tf — parameterized by color
variable "deployment_color" {
  type    = string
  default = "blue"
  validation {
    condition     = contains(["blue", "green"], var.deployment_color)
    error_message = "Must be blue or green."
  }
}

locals {
  name_suffix = var.deployment_color
  # Non-overlapping address spaces
  address_spaces = {
    blue  = "10.0.0.0/16"
    green = "10.1.0.0/16"
  }
}

resource "azurerm_virtual_network" "hub" {
  name                = "vnet-hub-${local.name_suffix}"
  address_space       = [local.address_spaces[var.deployment_color]]
  location            = var.location
  resource_group_name = "rg-network-${local.name_suffix}"
}
```

#### Traffic Switch Script

```bash
#!/bin/bash
# switch-traffic.sh — atomically switch from blue to green
set -euo pipefail

CURRENT_COLOR=$1  # "blue" or "green"
TARGET_COLOR=$2

echo "Switching traffic from $CURRENT_COLOR to $TARGET_COLOR..."

# 1. Validate target environment is healthy
echo "Validating $TARGET_COLOR environment..."
./tests/network/smoke-tests.sh --environment $TARGET_COLOR
if [ $? -ne 0 ]; then
    echo "❌ Target environment failed health checks. Aborting switch."
    exit 1
fi

# 2. Update DNS / Traffic Manager
az network traffic-manager endpoint update \
    --resource-group rg-traffic-manager \
    --profile-name tm-network \
    --name "endpoint-$CURRENT_COLOR" \
    --type azureEndpoints \
    --endpoint-status Disabled

az network traffic-manager endpoint update \
    --resource-group rg-traffic-manager \
    --profile-name tm-network \
    --name "endpoint-$TARGET_COLOR" \
    --type azureEndpoints \
    --endpoint-status Enabled

# 3. Wait for propagation
echo "Waiting 60s for traffic propagation..."
sleep 60

# 4. Verify traffic is flowing to new environment
./tests/network/verify-active-path.sh --expected $TARGET_COLOR

echo "✅ Traffic successfully switched to $TARGET_COLOR"
```

### Canary Routing Changes

#### Progressive Route Deployment

```hcl
# Deploy route change to 10% of traffic first using weighted routing
resource "azurerm_traffic_manager_endpoint" "canary" {
  name                = "canary-endpoint"
  resource_group_name = var.resource_group_name
  profile_name        = azurerm_traffic_manager_profile.network.name
  type                = "azureEndpoints"
  target_resource_id  = azurerm_public_ip.canary_lb.id
  weight              = 10  # 10% of traffic
}

resource "azurerm_traffic_manager_endpoint" "stable" {
  name                = "stable-endpoint"
  resource_group_name = var.resource_group_name
  profile_name        = azurerm_traffic_manager_profile.network.name
  type                = "azureEndpoints"
  target_resource_id  = azurerm_public_ip.stable_lb.id
  weight              = 90  # 90% of traffic
}
```

#### Canary Pipeline with Automated Rollback

```yaml
name: Canary Network Deployment

jobs:
  deploy-canary:
    runs-on: ubuntu-latest
    environment: canary
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Canary Region
        run: |
          terraform apply -auto-approve \
            -var-file="environments/prod.tfvars" \
            -var="deploy_regions=[\"eastus\"]" \
            -target=module.network_eastus

      - name: Monitor Canary (5 minutes)
        id: canary-check
        run: |
          START_TIME=$(date +%s)
          DURATION=300  # 5 minutes
          
          while [ $(($(date +%s) - START_TIME)) -lt $DURATION ]; do
            # Check error rate
            ERROR_RATE=$(az monitor metrics list \
              --resource "/subscriptions/.../loadBalancers/lb-canary" \
              --metric "HealthProbeStatus" \
              --aggregation Average \
              --interval PT1M \
              --query "value[0].timeseries[0].data[-1].average" -o tsv)
            
            if (( $(echo "$ERROR_RATE < 95" | bc -l) )); then
              echo "canary_healthy=false" >> $GITHUB_OUTPUT
              echo "::error::Canary health dropped below 95% — rolling back"
              break
            fi
            sleep 30
          done
          echo "canary_healthy=true" >> $GITHUB_OUTPUT

      - name: Rollback Canary
        if: steps.canary-check.outputs.canary_healthy == 'false'
        run: |
          git checkout HEAD~1 -- infrastructure/network/
          terraform apply -auto-approve \
            -var-file="environments/prod.tfvars" \
            -var="deploy_regions=[\"eastus\"]" \
            -target=module.network_eastus

  deploy-remaining:
    needs: deploy-canary
    if: needs.deploy-canary.outputs.canary_healthy == 'true'
    runs-on: ubuntu-latest
    environment: production
    strategy:
      matrix:
        region: [westus2, westeurope, southeastasia]
      max-parallel: 1  # One region at a time
    steps:
      - name: Deploy to ${{ matrix.region }}
        run: |
          terraform apply -auto-approve \
            -var-file="environments/prod.tfvars" \
            -var="deploy_regions=[\"${{ matrix.region }}\"]" \
            -target=module.network_${{ matrix.region }}

      - name: Validate Region
        run: ./tests/network/smoke-tests.sh --region ${{ matrix.region }}
```

### Change Windows and Maintenance Modes

#### Maintenance Window Enforcement

```yaml
# Prevent deployments outside maintenance windows
- name: Check Maintenance Window
  run: |
    CURRENT_HOUR=$(date -u +%H)
    CURRENT_DAY=$(date -u +%u)  # 1=Monday, 7=Sunday
    
    # Maintenance window: Tuesday-Thursday, 02:00-06:00 UTC
    if [ "$CURRENT_DAY" -lt 2 ] || [ "$CURRENT_DAY" -gt 4 ]; then
      echo "::error::Network deployments only allowed Tuesday-Thursday"
      exit 1
    fi
    
    if [ "$CURRENT_HOUR" -lt 2 ] || [ "$CURRENT_HOUR" -ge 6 ]; then
      echo "::error::Network deployments only allowed 02:00-06:00 UTC"
      exit 1
    fi
    
    echo "✅ Within maintenance window — proceeding"
```

#### Pre-Change Health Snapshot

```yaml
- name: Capture Pre-Change Baseline
  run: |
    # Capture current state for comparison
    az network watcher show-topology \
      --resource-group ${{ vars.NETWORK_RG }} \
      -o json > pre-change-topology.json
    
    # Capture current effective routes
    az network nic show-effective-route-table \
      --resource-group ${{ vars.NETWORK_RG }} \
      --name "nic-monitoring-vm" \
      -o json > pre-change-routes.json
    
    # Capture NSG effective rules
    az network nic list-effective-nsg \
      --resource-group ${{ vars.NETWORK_RG }} \
      --name "nic-monitoring-vm" \
      -o json > pre-change-nsg.json

- name: Upload Baseline Artifacts
  uses: actions/upload-artifact@v4
  with:
    name: pre-change-baseline
    path: pre-change-*.json
    retention-days: 30
```

### Rollback Triggers

#### Automated Rollback on Failure

```yaml
- name: Apply Network Changes
  id: apply
  run: terraform apply -auto-approve tfplan
  continue-on-error: true

- name: Post-Apply Health Check
  id: health
  if: steps.apply.outcome == 'success'
  run: |
    sleep 60  # Wait for propagation
    ./tests/network/smoke-tests.sh
  continue-on-error: true

- name: Automated Rollback
  if: steps.apply.outcome == 'failure' || steps.health.outcome == 'failure'
  run: |
    echo "::warning::Deployment failed — initiating rollback"
    
    # Revert to previous known-good state
    git checkout HEAD~1 -- infrastructure/network/
    terraform init
    terraform apply -auto-approve \
      -var-file="environments/prod.tfvars"
    
    # Verify rollback
    ./tests/network/smoke-tests.sh
    
    # Alert team
    curl -X POST "${{ secrets.SLACK_WEBHOOK }}" \
      -d '{"text":"⚠️ Network deployment ROLLED BACK. Check GitHub Actions for details."}'
```

#### Health-Based Rollback Triggers

```yaml
- name: Monitor Post-Deploy (10 minutes)
  run: |
    CHECKS_PASSED=0
    CHECKS_TOTAL=20
    
    for i in $(seq 1 $CHECKS_TOTAL); do
      # Check Azure Monitor metric
      LATENCY=$(az monitor metrics list \
        --resource "/subscriptions/.../connections/vpn-connection" \
        --metric "TunnelAverageBandwidth" \
        --aggregation Average \
        --interval PT1M \
        --query "value[0].timeseries[0].data[-1].average" -o tsv 2>/dev/null || echo "0")
      
      if (( $(echo "$LATENCY > 0" | bc -l) )); then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
      fi
      
      sleep 30
    done
    
    SUCCESS_RATE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))
    echo "Health check success rate: $SUCCESS_RATE%"
    
    if [ $SUCCESS_RATE -lt 80 ]; then
      echo "::error::Health check success rate below 80% — triggering rollback"
      exit 1
    fi
```

### Blast Radius Control

#### Region-by-Region Deployment

```yaml
strategy:
  matrix:
    region: [eastus, westus2, westeurope, southeastasia]
  max-parallel: 1  # Sequential — one region at a time
  fail-fast: true   # Stop all if one fails

steps:
  - name: Deploy to ${{ matrix.region }}
    run: |
      terraform workspace select ${{ matrix.region }}
      terraform apply -auto-approve -var-file="regions/${{ matrix.region }}.tfvars"

  - name: Validate ${{ matrix.region }}
    run: ./tests/validate-region.sh ${{ matrix.region }}

  - name: Wait Between Regions
    run: sleep 300  # 5 minute soak time between regions
```

#### Stack Isolation

```
infrastructure/network/
├── hub/                 # Deployed independently
│   ├── main.tf
│   └── terraform.tfstate
├── spokes/              # Depends on hub
│   ├── main.tf
│   └── terraform.tfstate
├── firewall/            # Depends on hub
│   ├── main.tf
│   └── terraform.tfstate
├── dns/                 # Depends on hub
│   ├── main.tf
│   └── terraform.tfstate
└── peering/             # Depends on hub + spokes
    ├── main.tf
    └── terraform.tfstate
```

Each stack:
- Has its own state file (blast radius limited to that stack)
- Can be rolled back independently
- Has explicit dependency ordering in the pipeline
- Failed stack doesn't block unrelated stacks

#### Deployment Ordering with Dependencies

```yaml
jobs:
  deploy-hub:
    # Always first — foundational
    steps: [...]
    outputs:
      hub_vnet_id: ${{ steps.output.outputs.vnet_id }}

  deploy-firewall:
    needs: deploy-hub
    steps: [...]

  deploy-spokes:
    needs: deploy-hub
    strategy:
      matrix:
        spoke: [app, data, mgmt]
      fail-fast: false  # Don't fail other spokes if one fails
    steps: [...]

  deploy-peering:
    needs: [deploy-hub, deploy-spokes]
    steps: [...]

  deploy-routes:
    needs: [deploy-firewall, deploy-peering]
    steps: [...]
```

### Post-Deployment Validation Gates

```yaml
- name: Post-Deploy Gate
  run: |
    echo "=== Post-Deployment Validation ==="
    GATE_PASS=true
    
    # Gate 1: All peerings connected
    PEERING_STATUS=$(az network vnet peering list \
      --resource-group $RG --vnet-name $VNET \
      --query "[?peeringState!='Connected'].name" -o tsv)
    if [ -n "$PEERING_STATUS" ]; then
      echo "❌ GATE FAIL: Disconnected peerings: $PEERING_STATUS"
      GATE_PASS=false
    fi
    
    # Gate 2: Firewall healthy
    FW_STATUS=$(az network firewall show \
      --name $FW_NAME --resource-group $RG \
      --query "provisioningState" -o tsv)
    if [ "$FW_STATUS" != "Succeeded" ]; then
      echo "❌ GATE FAIL: Firewall state: $FW_STATUS"
      GATE_PASS=false
    fi
    
    # Gate 3: VPN tunnels up
    TUNNEL_STATUS=$(az network vpn-connection show \
      --name $VPN_CONN --resource-group $RG \
      --query "connectionStatus" -o tsv)
    if [ "$TUNNEL_STATUS" != "Connected" ]; then
      echo "❌ GATE FAIL: VPN tunnel: $TUNNEL_STATUS"
      GATE_PASS=false
    fi
    
    # Gate 4: DNS resolution
    if ! nslookup app.internal.contoso.com > /dev/null 2>&1; then
      echo "❌ GATE FAIL: DNS resolution broken"
      GATE_PASS=false
    fi
    
    if [ "$GATE_PASS" = false ]; then
      echo "::error::Post-deployment gates FAILED — triggering rollback"
      exit 1
    fi
    
    echo "✅ All post-deployment gates passed"
```

### Change Management Checklist

```yaml
# .github/PULL_REQUEST_TEMPLATE/network-change.md
## Network Change Request

### Change Description
<!-- What is being changed and why? -->

### Risk Assessment
- [ ] Blast radius: [ ] Single resource [ ] Single VNet [ ] Multiple VNets [ ] Cross-region
- [ ] Requires maintenance window: Yes / No
- [ ] Rollback plan documented below

### Pre-Change Checklist
- [ ] Terraform plan reviewed (no unexpected destroys)
- [ ] Security scan passed (Checkov/Trivy config scanning)
- [ ] Policy compliance verified
- [ ] Peer review completed (2+ approvals)
- [ ] Change advisory board notified (if cross-region)

### Rollback Plan
<!-- Exact steps to revert if something goes wrong -->
1. 
2. 
3. 

### Post-Change Validation
- [ ] Connectivity smoke tests pass
- [ ] No new drift detected
- [ ] Monitoring dashboards normal
- [ ] On-call team notified of change completion
```

## Best Practices

1. **Git revert is the safest rollback** — Reverting code and re-running the pipeline is more reliable than state manipulation
2. **Never skip validation on rollback** — A rollback is just another deployment; run the same tests
3. **Soak time between regions** — Wait 5-10 minutes between regional deployments to catch latent issues
4. **Fail-fast in canary, fail-safe in prod** — Stop canary on first failure; in prod, isolate the failure
5. **State backups before every apply** — Automated state backup enables point-in-time recovery
6. **Maintenance windows for high-risk changes** — VPN, ExpressRoute, and firewall changes need planned windows
7. **Document rollback in the PR** — Every network PR template should include an explicit rollback plan
8. **Automated health gates** — Don't rely on humans to notice failures; automate the decision
9. **Blast radius by design** — Split infrastructure into independent stacks with separate state files
10. **Post-mortem every rollback** — Every rollback is a learning opportunity; document what failed and why

---

**Analysis only — verify against vendor documentation before applying.**
