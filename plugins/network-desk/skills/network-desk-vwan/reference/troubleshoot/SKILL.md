# vwan_troubleshoot — Virtual WAN Troubleshooting and Diagnostics

## Overview

This skill provides structured troubleshooting procedures for Azure Virtual WAN environments, including effective route inspection, connection state verification, routing intent conflicts, BGP diagnostics, and resolution steps for the most common connectivity failures. All commands use the Azure CLI and assume the operator has Network Contributor or Reader permissions on the vWAN resource group.

## Checking Effective Routes on the Hub

The most critical diagnostic command in vWAN is `az network vhub get-effective-routes`, which returns the programmed routes in the hub's route table including their source (BGP, static, routing intent) and next hop.

```bash
# Get effective routes for the hub's default route table
az network vhub get-effective-routes \
  --name "hub-eastus" \
  --resource-group "rg-networking" \
  --resource-type "RouteTable" \
  --resource-id "/subscriptions/{sub-id}/resourceGroups/rg-networking/providers/Microsoft.Network/virtualHubs/hub-eastus/hubRouteTables/defaultRouteTable" \
  --output json

# Get effective routes for a specific VNet connection
az network vhub get-effective-routes \
  --name "hub-eastus" \
  --resource-group "rg-networking" \
  --resource-type "HubVirtualNetworkConnection" \
  --resource-id "/subscriptions/{sub-id}/resourceGroups/rg-networking/providers/Microsoft.Network/virtualHubs/hub-eastus/hubVirtualNetworkConnections/conn-spoke-web" \
  --output json

# Get effective routes for a VPN gateway connection
az network vhub get-effective-routes \
  --name "hub-eastus" \
  --resource-group "rg-networking" \
  --resource-type "VpnConnection" \
  --resource-id "/subscriptions/{sub-id}/resourceGroups/rg-networking/providers/Microsoft.Network/vpnGateways/vpn-gw-eastus/vpnConnections/conn-branch-newyork" \
  --output json
```

Inspect the output for:

- **addressPrefixes:** The destination CIDR blocks
- **nextHops:** The next-hop resource IDs (firewall, NVA, VPN gateway, or hub router)
- **routeOrigin:** How the route was learned — `Service`, `HubRouteTable`, `DefaultRouteTable`, or the originating connection

## Connection State Verification

```bash
# Check VPN gateway provisioning state and connection status
az network vpn-gateway show \
  --name "vpn-gw-eastus" \
  --resource-group "rg-networking" \
  --query "{provisioningState:provisioningState,vpnConnections:connections[].{name:name,connectionStatus:connectionStatus,ingressBytesTransferred:ingressBytesTransferred,egressBytesTransferred:egressBytesTransferred}}" \
  --output json

# Check ExpressRoute gateway connection status
az network express-route gateway connection show \
  --name "conn-er-datacenter" \
  --resource-group "rg-networking" \
  --gateway-name "er-gw-eastus" \
  --query "{provisioningState:provisioningState,routingConfiguration:routingConfiguration}" \
  --output json

# Check VNet connection status
az network vhub connection show \
  --name "conn-spoke-web" \
  --resource-group "rg-networking" \
  --vhub-name "hub-eastus" \
  --query "{provisioningState:provisioningState,enableInternetSecurity:enableInternetSecurity,routingConfiguration:routingConfiguration}" \
  --output json
```

## Routing Intent Conflicts and Resolution

Common routing intent conflicts:

1. **Conflict with existing static routes:** Routing intent overrides static routes in the default route table. If custom static routes exist, they may be removed or ignored after enabling routing intent. **Resolution:** Remove conflicting static routes before enabling routing intent. Use routing intent as the sole routing mechanism.

2. **Multiple next-hop resources:** Internet and private traffic policies must use the same next-hop type (both Azure Firewall or both NVA, but not a mix in the same policy). **Resolution:** If you need different security stacks for internet vs private traffic, consider using a single NVA that handles both, or chain via BGP.

3. **VNet connection `internetSecurity` mismatch:** If routing intent is enabled but specific VNet connections have `internetSecurity=false`, those spokes will not receive the default route. **Resolution:** Update the VNet connection:

```bash
az network vhub connection update \
  --name "conn-spoke-web" \
  --resource-group "rg-networking" \
  --vhub-name "hub-eastus" \
  --internet-security true
```

## BGP Learned Routes from NVA

To inspect BGP routes learned from an NVA or spoke-based BGP peer:

```bash
# List BGP connections on the hub
az network vhub bgpconnection list \
  --resource-group "rg-networking" \
  --vhub-name "hub-eastus" \
  --output table

# Show learned routes from a specific BGP connection
az network vhub bgpconnection list-learned-routes \
  --name "bgp-to-spoke-nva" \
  --resource-group "rg-networking" \
  --vhub-name "hub-eastus" \
  --output json

# Show advertised routes to a specific BGP peer
az network vhub bgpconnection list-advertised-routes \
  --name "bgp-to-spoke-nva" \
  --resource-group "rg-networking" \
  --vhub-name "hub-eastus" \
  --output json
```

Verify that:

- The NVA's ASN is not 65520 (reserved for the hub router)
- Expected prefixes appear in learned routes with correct next-hop IPs
- The BGP session state shows `Connected` (not `Idle` or `Active`)

## Common Issues and Troubleshooting Steps

### Issue 1: Spoke Cannot Reach Spoke

**Symptoms:** VMs in spoke-A cannot ping or connect to VMs in spoke-B, both connected to the same hub.

**Troubleshooting steps:**

1. Verify both VNet connections are in `Succeeded` provisioning state
2. Check effective routes on both VNet connections — confirm each spoke's prefix appears in the other's routes
3. If routing intent (private traffic policy) is enabled, verify Azure Firewall has a network rule allowing traffic between the spoke ranges
4. Check NSGs on source and destination subnets for deny rules
5. Verify there are no conflicting UDRs on spoke subnets overriding hub-injected routes

```bash
# Verify spoke-A effective routes include spoke-B prefix
az network vhub get-effective-routes \
  --name "hub-eastus" \
  --resource-group "rg-networking" \
  --resource-type "HubVirtualNetworkConnection" \
  --resource-id "/subscriptions/{sub-id}/resourceGroups/rg-networking/providers/Microsoft.Network/virtualHubs/hub-eastus/hubVirtualNetworkConnections/conn-spoke-a"
```

### Issue 2: Internet Breakout Not Working

**Symptoms:** VMs in spoke VNets cannot reach the internet despite routing intent internet traffic policy being enabled.

**Troubleshooting steps:**

1. Confirm routing intent is enabled and the internet traffic policy has the correct next-hop (Azure Firewall or NVA)
2. Verify the VNet connection has `internetSecurity=true`
3. Check effective routes on the spoke — 0.0.0.0/0 should point to the firewall/NVA
4. Verify Azure Firewall application rules or network rules allow outbound internet access
5. Check Azure Firewall diagnostic logs for denied traffic

```bash
az network vhub routing-intent show \
  --name "routing-intent-eastus" \
  --resource-group "rg-networking" \
  --vhub "hub-eastus" \
  --query "routingPolicies[?destinations[0]=='Internet']"
```

### Issue 3: ExpressRoute Routes Not Propagating

**Symptoms:** On-premises prefixes learned via ExpressRoute do not appear in spoke VNet effective routes.

**Troubleshooting steps:**

1. Verify the ExpressRoute circuit is in `Provisioned` state with the provider
2. Confirm private peering is configured and BGP sessions are established
3. Check the ExpressRoute gateway connection state in the hub
4. Verify route filters are not blocking expected prefixes
5. If routing intent private policy is active, confirm that on-premises prefixes are not being overridden by RFC1918 supernets

```bash
az network express-route show \
  --name "er-circuit-datacenter" \
  --resource-group "rg-er" \
  --query "{circuitProvisioningState:circuitProvisioningState,serviceProviderProvisioningState:serviceProviderProvisioningState,peerings:peerings[].{name:name,state:state,peerASN:peerASN}}" \
  --output json
```

### Issue 4: VPN Tunnel Not Establishing

**Symptoms:** S2S VPN connection shows `NotConnected` or `Connecting` status indefinitely.

**Troubleshooting steps:**

1. Verify the VPN site public IP is correct and reachable
2. Confirm pre-shared key matches on both ends
3. Check IKE/IPsec proposals — hub defaults may not match branch CPE configuration
4. Verify BGP ASN on the VPN site matches the branch router's configured ASN
5. Check for NAT or firewall rules blocking UDP 500/4500 on the branch side

```bash
az network vpn-gateway connection show \
  --name "conn-branch-newyork" \
  --resource-group "rg-networking" \
  --gateway-name "vpn-gw-eastus" \
  --query "{connectionStatus:connectionStatus,sharedKey:sharedKey,enableBgp:enableBgp,ipsecPolicies:ipsecPolicies}"
```

### Issue 5: NVA Not Receiving Traffic

**Symptoms:** Traffic between spokes or from branches bypasses the NVA even though it should be the next hop.

**Troubleshooting steps:**

1. Verify routing intent is configured with the NVA as the next hop (not Azure Firewall)
2. Check the NVA resource ID in the routing intent policy matches the deployed NVA
3. Confirm BGP peering between the NVA and hub router is in `Connected` state
4. Verify the NVA is advertising routes and the hub is learning them
5. Check NVA health — ensure the appliance is forwarding traffic (IP forwarding enabled, interfaces up)

```bash
az network virtual-appliance show \
  --name "nva-fortinet-eastus" \
  --resource-group "rg-networking" \
  --query "{provisioningState:provisioningState,virtualApplianceAsn:virtualApplianceAsn,virtualApplianceNics:virtualApplianceNics}" \
  --output json
```

## Diagnostic Tools

### Network Watcher

- **IP Flow Verify:** Test if a packet is allowed or denied by NSG rules between source and destination
- **Next Hop:** Determine the next hop for a packet from a spoke VM — validates that the hub-injected route is effective at the VM level
- **Connection Troubleshoot:** End-to-end connectivity test including latency and packet loss

```bash
az network watcher test-ip-flow \
  --direction Outbound \
  --local "10.1.0.4:*" \
  --remote "10.2.0.4:443" \
  --protocol TCP \
  --vm "/subscriptions/{sub-id}/resourceGroups/rg-spokes/providers/Microsoft.Compute/virtualMachines/vm-spoke-a" \
  --output json
```

### Connection Monitor

Configure continuous monitoring of branch-to-spoke and spoke-to-spoke connectivity. Connection Monitor uses the Network Watcher agent extension on VMs and supports TCP, ICMP, and HTTP test protocols. Alerts can be triggered on latency thresholds or connectivity loss.

## Reference

- vWAN troubleshooting: https://learn.microsoft.com/en-us/azure/virtual-wan/virtual-wan-troubleshoot
- Effective routes: https://learn.microsoft.com/en-us/azure/virtual-wan/effective-routes-virtual-hub
- Network Watcher: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-overview

**Analysis only — verify against vendor documentation before applying.**
