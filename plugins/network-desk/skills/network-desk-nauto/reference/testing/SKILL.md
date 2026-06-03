# Network Configuration Testing

## Purpose

Validate that network infrastructure deployments are correct, connectivity works as expected, and configurations meet compliance requirements — automatically, as part of the CI/CD pipeline. Network testing catches misconfigurations before they impact production workloads.

## Core Knowledge

### Testing Pyramid for Network Infrastructure

```
          ┌──────────────┐
          │   Chaos      │  ← Resilience (periodic)
          │  Engineering │
         ─┼──────────────┼─
         │  Integration   │  ← Cross-stack connectivity
         │   Tests        │
        ─┼────────────────┼─
        │  Smoke Tests     │  ← Post-deploy reachability
        │  (Connectivity)  │
       ─┼──────────────────┼─
       │  Compliance Tests  │  ← Policy conformance
       │  (Resource state)  │
      ─┼────────────────────┼─
      │   Unit Tests         │  ← IaC validation (plan-level)
      │   (Terraform plan)   │
      └──────────────────────┘
```

### Terratest for Infrastructure Validation

#### Azure VNet Validation

```go
// test/network_test.go
package test

import (
    "testing"
    "fmt"
    
    "github.com/gruntwork-io/terratest/modules/azure"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestHubNetwork(t *testing.T) {
    t.Parallel()

    subscriptionID := "your-subscription-id"
    resourceGroup := "rg-network-test"

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../infrastructure/network/hub",
        Vars: map[string]interface{}{
            "environment":    "test",
            "address_space":  []string{"10.99.0.0/16"},
            "resource_group": resourceGroup,
        },
    })

    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)

    // Validate VNet was created
    vnetName := terraform.Output(t, terraformOptions, "vnet_name")
    vnet := azure.GetVirtualNetwork(t, vnetName, resourceGroup, subscriptionID)
    
    assert.Equal(t, "Succeeded", *vnet.ProvisioningState)
    assert.Contains(t, *vnet.AddressSpace.AddressPrefixes, "10.99.0.0/16")

    // Validate subnets exist
    subnets := azure.GetSubnetsForVirtualNetwork(t, vnetName, resourceGroup, subscriptionID)
    subnetNames := []string{}
    for _, s := range subnets {
        subnetNames = append(subnetNames, s)
    }
    assert.Contains(t, subnetNames, "AzureFirewallSubnet")
    assert.Contains(t, subnetNames, "GatewaySubnet")
    assert.Contains(t, subnetNames, "snet-management")

    // Validate NSG assignment
    nsgID := terraform.Output(t, terraformOptions, "management_subnet_nsg_id")
    assert.NotEmpty(t, nsgID)
}

func TestPeeringConnectivity(t *testing.T) {
    t.Parallel()

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../infrastructure/network/peering",
        Vars: map[string]interface{}{
            "environment": "test",
        },
    })

    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)

    // Validate peering status
    peeringState := terraform.Output(t, terraformOptions, "peering_state")
    assert.Equal(t, "Connected", peeringState)
    
    // Validate peering allows gateway transit
    gatewayTransit := terraform.Output(t, terraformOptions, "allow_gateway_transit")
    assert.Equal(t, "true", gatewayTransit)
}
```

#### AWS VPC Validation with Terratest

```go
func TestVPCConfiguration(t *testing.T) {
    t.Parallel()

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../infrastructure/network/vpc",
        Vars: map[string]interface{}{
            "environment": "test",
            "vpc_cidr":    "10.99.0.0/16",
        },
    })

    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)

    vpcID := terraform.Output(t, terraformOptions, "vpc_id")
    
    // Verify VPC exists and has correct CIDR
    vpc := aws.GetVpcById(t, vpcID, "us-east-1")
    assert.Equal(t, "10.99.0.0/16", vpc.CidrBlock)
    
    // Verify flow logs are enabled
    flowLogs := aws.GetVpcFlowLogs(t, vpcID, "us-east-1")
    require.NotEmpty(t, flowLogs, "VPC must have flow logs enabled")
    
    // Verify no internet gateway (private VPC)
    igws := aws.GetInternetGatewaysForVpc(t, vpcID, "us-east-1")
    assert.Empty(t, igws, "Production VPC should not have an Internet Gateway")
}
```

### Pester Tests for Azure Network Resources

```powershell
# tests/Network.Tests.ps1

Describe "Hub Network Configuration" {
    BeforeAll {
        $resourceGroup = "rg-network-prod"
        $vnetName = "vnet-hub-prod"
        $vnet = Get-AzVirtualNetwork -Name $vnetName -ResourceGroupName $resourceGroup
    }

    Context "VNet Configuration" {
        It "Should exist and be provisioned" {
            $vnet.ProvisioningState | Should -Be "Succeeded"
        }

        It "Should have correct address space" {
            $vnet.AddressSpace.AddressPrefixes | Should -Contain "10.0.0.0/16"
        }

        It "Should have DNS servers configured" {
            $vnet.DhcpOptions.DnsServers | Should -Not -BeNullOrEmpty
        }

        It "Should have DDoS protection enabled" {
            $vnet.EnableDdosProtection | Should -Be $true
        }
    }

    Context "Subnet Configuration" {
        It "Should have required subnets" {
            $subnetNames = $vnet.Subnets.Name
            $subnetNames | Should -Contain "AzureFirewallSubnet"
            $subnetNames | Should -Contain "GatewaySubnet"
            $subnetNames | Should -Contain "snet-shared-services"
        }

        It "All workload subnets should have NSGs" {
            $workloadSubnets = $vnet.Subnets | Where-Object {
                $_.Name -notin @("AzureFirewallSubnet", "GatewaySubnet", "AzureBastionSubnet")
            }
            foreach ($subnet in $workloadSubnets) {
                $subnet.NetworkSecurityGroup | Should -Not -BeNullOrEmpty `
                    -Because "Subnet $($subnet.Name) must have an NSG attached"
            }
        }

        It "All workload subnets should have route tables" {
            $workloadSubnets = $vnet.Subnets | Where-Object {
                $_.Name -notin @("AzureFirewallSubnet", "GatewaySubnet", "AzureBastionSubnet")
            }
            foreach ($subnet in $workloadSubnets) {
                $subnet.RouteTable | Should -Not -BeNullOrEmpty `
                    -Because "Subnet $($subnet.Name) must have a route table for forced tunneling"
            }
        }
    }

    Context "NSG Rules" {
        BeforeAll {
            $nsg = Get-AzNetworkSecurityGroup -ResourceGroupName $resourceGroup -Name "nsg-shared-services"
        }

        It "Should deny inbound RDP from internet" {
            $rdpRule = $nsg.SecurityRules | Where-Object {
                $_.DestinationPortRange -eq "3389" -and
                $_.Direction -eq "Inbound" -and
                $_.SourceAddressPrefix -eq "*"
            }
            $rdpRule.Access | Should -Be "Deny" -Because "RDP from internet must be blocked"
        }

        It "Should deny inbound SSH from internet" {
            $sshRule = $nsg.SecurityRules | Where-Object {
                $_.DestinationPortRange -eq "22" -and
                $_.Direction -eq "Inbound" -and
                $_.SourceAddressPrefix -eq "*"
            }
            $sshRule.Access | Should -Be "Deny" -Because "SSH from internet must be blocked"
        }
    }

    Context "Route Tables" {
        BeforeAll {
            $rt = Get-AzRouteTable -ResourceGroupName $resourceGroup -Name "rt-default"
        }

        It "Should have default route to firewall" {
            $defaultRoute = $rt.Routes | Where-Object { $_.AddressPrefix -eq "0.0.0.0/0" }
            $defaultRoute | Should -Not -BeNullOrEmpty
            $defaultRoute.NextHopType | Should -Be "VirtualAppliance"
        }
    }
}

Describe "VNet Peering" {
    BeforeAll {
        $hubVnet = Get-AzVirtualNetwork -Name "vnet-hub-prod" -ResourceGroupName "rg-network-prod"
        $peerings = Get-AzVirtualNetworkPeering -VirtualNetwork $hubVnet
    }

    It "All peerings should be Connected" {
        foreach ($peering in $peerings) {
            $peering.PeeringState | Should -Be "Connected" `
                -Because "Peering $($peering.Name) must be connected"
        }
    }

    It "Hub peerings should allow gateway transit" {
        foreach ($peering in $peerings) {
            $peering.AllowGatewayTransit | Should -Be $true `
                -Because "Hub must allow gateway transit to spokes"
        }
    }
}
```

```yaml
# Running Pester in CI
- name: Run Network Tests
  shell: pwsh
  run: |
    Install-Module -Name Pester -Force -Scope CurrentUser
    Install-Module -Name Az.Network -Force -Scope CurrentUser
    
    $config = New-PesterConfiguration
    $config.Run.Path = "./tests/Network.Tests.ps1"
    $config.Output.Verbosity = "Detailed"
    $config.TestResult.Enabled = $true
    $config.TestResult.OutputFormat = "NUnitXml"
    $config.TestResult.OutputPath = "./test-results.xml"
    
    Invoke-Pester -Configuration $config
```

### pytest + boto3 for AWS Network Validation

```python
# tests/test_network.py
import boto3
import pytest
from ipaddress import ip_network

ec2 = boto3.client('ec2', region_name='us-east-1')

@pytest.fixture
def vpc():
    """Get the production VPC."""
    response = ec2.describe_vpcs(
        Filters=[{'Name': 'tag:Environment', 'Values': ['production']}]
    )
    assert len(response['Vpcs']) == 1, "Expected exactly one production VPC"
    return response['Vpcs'][0]

@pytest.fixture
def security_groups(vpc):
    """Get all security groups in the VPC."""
    response = ec2.describe_security_groups(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc['VpcId']]}]
    )
    return response['SecurityGroups']

class TestVPCConfiguration:
    def test_vpc_cidr(self, vpc):
        """VPC should use the expected CIDR range."""
        assert vpc['CidrBlock'] == '10.0.0.0/16'

    def test_flow_logs_enabled(self, vpc):
        """VPC must have flow logs enabled."""
        response = ec2.describe_flow_logs(
            Filters=[{'Name': 'resource-id', 'Values': [vpc['VpcId']]}]
        )
        assert len(response['FlowLogs']) > 0, "VPC flow logs must be enabled"
        for log in response['FlowLogs']:
            assert log['FlowLogStatus'] == 'ACTIVE'
            assert log['TrafficType'] == 'ALL'

    def test_no_default_sg_rules(self, security_groups):
        """Default security group should have no ingress/egress rules."""
        default_sg = next(
            (sg for sg in security_groups if sg['GroupName'] == 'default'), None
        )
        assert default_sg is not None
        assert len(default_sg['IpPermissions']) == 0, \
            "Default SG should have no inbound rules"

class TestSecurityGroups:
    def test_no_unrestricted_ingress(self, security_groups):
        """No security group should allow 0.0.0.0/0 ingress on SSH/RDP."""
        restricted_ports = [22, 3389]
        for sg in security_groups:
            for rule in sg['IpPermissions']:
                from_port = rule.get('FromPort', 0)
                to_port = rule.get('ToPort', 65535)
                for port in restricted_ports:
                    if from_port <= port <= to_port:
                        for ip_range in rule.get('IpRanges', []):
                            assert ip_range['CidrIp'] != '0.0.0.0/0', \
                                f"SG {sg['GroupId']} allows {port} from 0.0.0.0/0"

    def test_all_sg_rules_have_description(self, security_groups):
        """All security group rules must have descriptions."""
        for sg in security_groups:
            for rule in sg['IpPermissions'] + sg['IpPermissionsEgress']:
                for ip_range in rule.get('IpRanges', []):
                    assert 'Description' in ip_range and ip_range['Description'], \
                        f"SG {sg['GroupId']} has rule without description"

class TestSubnets:
    def test_private_subnets_no_public_ip(self, vpc):
        """Private subnets should not auto-assign public IPs."""
        response = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc['VpcId']]},
                {'Name': 'tag:Tier', 'Values': ['private']}
            ]
        )
        for subnet in response['Subnets']:
            assert not subnet['MapPublicIpOnLaunch'], \
                f"Private subnet {subnet['SubnetId']} auto-assigns public IPs"

    def test_subnet_sizing(self, vpc):
        """All subnets should be at least /26 (64 IPs)."""
        response = ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc['VpcId']]}]
        )
        for subnet in response['Subnets']:
            network = ip_network(subnet['CidrBlock'])
            assert network.prefixlen <= 26, \
                f"Subnet {subnet['SubnetId']} is /{network.prefixlen} — too small"
```

```yaml
# CI integration
- name: Run Network Tests
  run: |
    pip install pytest boto3
    pytest tests/test_network.py -v --junitxml=test-results.xml
```

### Connectivity Testing After Deployment

#### Bash Smoke Tests

```bash
#!/bin/bash
# tests/network/smoke-tests.sh
set -euo pipefail

FIREWALL_IP="10.0.1.4"
DNS_SERVER="10.0.2.4"
APP_ENDPOINT="app.internal.contoso.com"

echo "=== Network Smoke Tests ==="

# Test 1: DNS resolution
echo "[TEST] DNS resolution for internal endpoints..."
if nslookup $APP_ENDPOINT $DNS_SERVER > /dev/null 2>&1; then
    echo "  ✅ DNS resolution working"
else
    echo "  ❌ DNS resolution failed"
    exit 1
fi

# Test 2: Firewall reachability from spoke
echo "[TEST] Firewall reachable from spoke network..."
if nc -z -w5 $FIREWALL_IP 443 2>/dev/null; then
    echo "  ✅ Firewall port 443 reachable"
else
    echo "  ❌ Cannot reach firewall"
    exit 1
fi

# Test 3: Outbound internet via firewall
echo "[TEST] Outbound internet connectivity..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://ifconfig.me)
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "  ✅ Outbound internet working"
else
    echo "  ❌ Outbound internet blocked (HTTP $HTTP_CODE)"
    exit 1
fi

# Test 4: Cross-spoke connectivity should be blocked (zero-trust)
echo "[TEST] Cross-spoke traffic blocked (zero-trust)..."
if nc -z -w3 10.1.2.4 443 2>/dev/null; then
    echo "  ❌ Cross-spoke traffic NOT blocked — security violation!"
    exit 1
else
    echo "  ✅ Cross-spoke traffic correctly blocked"
fi

echo ""
echo "=== All smoke tests passed ==="
```

#### PowerShell Connectivity Tests

```powershell
# tests/connectivity/Test-NetworkConnectivity.ps1

param(
    [string]$Environment = "prod",
    [string]$ConfigFile = "./tests/connectivity/endpoints.json"
)

$endpoints = Get-Content $ConfigFile | ConvertFrom-Json

$results = @()

foreach ($endpoint in $endpoints.$Environment) {
    $result = [PSCustomObject]@{
        Name    = $endpoint.name
        Target  = $endpoint.host
        Port    = $endpoint.port
        Status  = "Unknown"
    }

    try {
        $test = Test-NetConnection -ComputerName $endpoint.host -Port $endpoint.port -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) {
            $result.Status = "PASS"
        } else {
            $result.Status = "FAIL"
        }
    } catch {
        $result.Status = "ERROR: $_"
    }

    $results += $result
}

$results | Format-Table -AutoSize

$failures = $results | Where-Object { $_.Status -ne "PASS" }
if ($failures.Count -gt 0) {
    Write-Error "❌ $($failures.Count) connectivity tests failed"
    exit 1
}

Write-Host "✅ All $($results.Count) connectivity tests passed" -ForegroundColor Green
```

```json
// tests/connectivity/endpoints.json
{
  "prod": [
    { "name": "SQL Database", "host": "sql-prod.database.windows.net", "port": 1433 },
    { "name": "Storage (Private)", "host": "stprod.blob.core.windows.net", "port": 443 },
    { "name": "Key Vault", "host": "kv-prod.vault.azure.net", "port": 443 },
    { "name": "Internal API", "host": "api.internal.contoso.com", "port": 443 }
  ],
  "staging": [
    { "name": "SQL Database", "host": "sql-staging.database.windows.net", "port": 1433 },
    { "name": "Storage (Private)", "host": "ststaging.blob.core.windows.net", "port": 443 }
  ]
}
```

### Integration Test Patterns

```go
// test/integration_test.go
// Test that spoke workloads can reach shared services through the hub

func TestSpokeToSharedServices(t *testing.T) {
    // Deploy a test VM in the spoke
    spokeVMIP := terraform.Output(t, spokeOptions, "test_vm_private_ip")
    
    // Run connectivity test from the spoke VM via Azure Run Command
    result := azure.RunCommandOnVM(t, subscriptionID, resourceGroup, "vm-test-spoke",
        azure.RunCommandInput{
            CommandId: "RunShellScript",
            Script: []string{
                fmt.Sprintf("curl -s -o /dev/null -w '%%{http_code}' https://%s", sharedServiceEndpoint),
            },
        },
    )
    
    assert.Contains(t, result, "200", "Spoke should reach shared services via hub firewall")
}

func TestSpokeToSpokeBlocked(t *testing.T) {
    // Cross-spoke traffic should be denied
    result := azure.RunCommandOnVM(t, subscriptionID, resourceGroup, "vm-test-spoke-a",
        azure.RunCommandInput{
            CommandId: "RunShellScript",
            Script: []string{
                fmt.Sprintf("nc -z -w3 %s 443 && echo 'CONNECTED' || echo 'BLOCKED'", spokeBPrivateIP),
            },
        },
    )
    
    assert.Contains(t, result, "BLOCKED", "Spoke-to-spoke traffic must be blocked")
}
```

### Chaos Engineering for Network Resilience

#### Azure Chaos Studio Experiment

```json
{
  "identity": {
    "type": "SystemAssigned"
  },
  "properties": {
    "selectors": [
      {
        "type": "List",
        "id": "selector-nsg",
        "targets": [
          {
            "type": "ChaosTarget",
            "id": "/subscriptions/.../networkSecurityGroups/nsg-app/providers/Microsoft.Chaos/targets/Microsoft-NetworkSecurityGroup"
          }
        ]
      }
    ],
    "steps": [
      {
        "name": "Block-Outbound-Traffic",
        "branches": [
          {
            "name": "branch-1",
            "actions": [
              {
                "type": "continuous",
                "name": "urn:csci:microsoft:networkSecurityGroup:securityRule/1.0",
                "duration": "PT5M",
                "parameters": [
                  { "key": "direction", "value": "Outbound" },
                  { "key": "destinationAddresses", "value": "[\"10.0.2.0/24\"]" },
                  { "key": "action", "value": "Deny" },
                  { "key": "destinationPortRanges", "value": "[\"443\"]" },
                  { "key": "protocol", "value": "TCP" },
                  { "key": "priority", "value": "100" },
                  { "key": "name", "value": "chaos-deny-outbound" }
                ],
                "selectorId": "selector-nsg"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

#### Chaos Experiment in CI Pipeline

```yaml
- name: Run Chaos Experiment
  if: github.ref == 'refs/heads/main' && vars.RUN_CHAOS == 'true'
  run: |
    # Start experiment
    EXPERIMENT_ID=$(az rest --method POST \
      --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Chaos/experiments/$EXPERIMENT_NAME/start?api-version=2023-11-01" \
      --query "statusUrl" -o tsv)
    
    # Wait for completion (max 10 minutes)
    for i in {1..20}; do
      STATUS=$(az rest --method GET --url "$EXPERIMENT_ID" --query "properties.status" -o tsv)
      if [ "$STATUS" == "Success" ]; then
        echo "✅ Chaos experiment passed — system resilient"
        break
      elif [ "$STATUS" == "Failed" ]; then
        echo "❌ Chaos experiment revealed vulnerability"
        exit 1
      fi
      sleep 30
    done
```

## Best Practices

1. **Test at every layer** — Unit tests for IaC, compliance tests for state, smoke tests for connectivity
2. **Test in isolated environments** — Never run destructive tests against production networks
3. **Ephemeral test infrastructure** — Create and destroy test VNets/VPCs per test run
4. **Parallel test execution** — Run independent tests concurrently (Terratest `t.Parallel()`)
5. **Meaningful assertions** — Test business-level outcomes ("app can reach database"), not just resource existence
6. **Negative testing** — Verify that traffic that should be blocked IS blocked
7. **Test failure modes** — Use chaos engineering to validate resilience, not just happy paths
8. **Fast feedback** — Run quick smoke tests on every PR; full integration tests nightly
9. **Test data management** — Use predictable, non-overlapping CIDR ranges for test environments
10. **Cleanup on failure** — Ensure `defer terraform.Destroy()` or equivalent always runs, even on test failure

---

**Analysis only — verify against vendor documentation before applying.**
