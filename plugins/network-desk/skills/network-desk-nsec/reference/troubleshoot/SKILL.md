# Skill: Network Security Troubleshooting (nsec_troubleshoot)

Troubleshoot blocked traffic, security rule misconfigurations, and connectivity issues caused by network security controls across Azure, AWS, and GCP.

---

## Blocked Traffic Debugging — Systematic Approach

When traffic is unexpectedly blocked, follow this checklist:

1. **Confirm the symptom**: Is the traffic truly blocked (timeout, RST, ICMP unreachable) or is it something else (DNS failure, application error, route issue)?
2. **Identify the security controls in the path**: List every NSG, SG, NACL, firewall, and WAF between source and destination.
3. **Test each control independently**: Use cloud-native tools (IP flow verify, Reachability Analyzer, connectivity tests) to pinpoint which control is blocking.
4. **Check both directions**: Stateful controls track connections — but NACLs are stateless, and asymmetric routing can cause stateful controls to fail.
5. **Verify effective rules**: The applied rules may differ from what's configured due to inheritance, priority, or default rules.

---

## Azure — IP Flow Verify and Effective Security Rules

### IP Flow Verify
Tests whether a specific 5-tuple (source IP, destination IP, protocol, source port, destination port) would be allowed or denied by NSG rules at a specific VM NIC. Does not send actual traffic — evaluates the NSG configuration.

```bash
# Test if TCP traffic from 10.0.1.4:49152 to 10.0.2.5:443 is allowed
az network watcher test-ip-flow \
  --direction Inbound \
  --protocol TCP \
  --local 10.0.2.5:443 \
  --remote 10.0.1.4:49152 \
  --vm MyVM \
  --nic MyVMNic \
  --resource-group MyRG

# Output example (blocked):
# {
#   "access": "Deny",
#   "ruleId": "/subscriptions/.../networkSecurityGroups/myNSG/securityRules/DenyAllInbound"
# }
```

### Effective Security Rules
Shows the complete set of evaluated rules for a NIC, including rules from both subnet-level and NIC-level NSGs, plus default rules.

```bash
# Show effective security rules for a NIC
az network nic list-effective-nsg \
  --name MyVMNic --resource-group MyRG \
  --query 'value[].effectiveSecurityRules[].{Priority:priority, Direction:direction, Access:access, Protocol:protocol, SrcPrefix:sourceAddressPrefix, DstPrefix:destinationAddressPrefix, DstPort:destinationPortRange}' \
  -o table
```

### NSG Diagnostics (Network Watcher)
Evaluates multiple NSG rules for a traffic flow, showing both subnet and NIC-level evaluation:

```bash
az network watcher run-configuration-diagnostic \
  --resource /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm} \
  --direction Inbound \
  --queries '[{"direction":"Inbound","protocol":"TCP","source":"10.0.1.4","destination":"10.0.2.5","destinationPort":"443"}]'
```

---

## AWS — VPC Reachability Analyzer

Analyzes the network path between two endpoints, testing reachability through all network components including security groups, NACLs, route tables, and gateways. Does not send actual traffic.

```bash
# Create a reachability analysis
aws ec2 create-network-insights-path \
  --source i-source123 \
  --destination i-dest456 \
  --protocol TCP \
  --destination-port 443

# Start analysis
aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-xxx

# Get results
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-xxx \
  --query 'NetworkInsightsAnalyses[0].{Reachable:NetworkPathFound, Explanations:Explanations}'
```

### Common NACL Issues
NACLs are **stateless** — inbound and outbound rules are evaluated independently. The most common NACL mistake is forgetting to allow ephemeral port return traffic:

```bash
# Inbound rule allows TCP 443 — but outbound must allow ephemeral ports back
# Outbound NACL rule needed:
aws ec2 create-network-acl-entry \
  --network-acl-id acl-xxx \
  --rule-number 100 \
  --protocol tcp \
  --port-range From=1024,To=65535 \
  --cidr-block 0.0.0.0/0 \
  --egress \
  --rule-action allow
```

### Security Group Debugging
```bash
# Show all rules for a security group
aws ec2 describe-security-groups \
  --group-ids sg-xxx \
  --query 'SecurityGroups[0].{Inbound:IpPermissions, Outbound:IpPermissionsEgress}'

# Check if an instance is associated with the expected SGs
aws ec2 describe-instances \
  --instance-ids i-xxx \
  --query 'Reservations[0].Instances[0].SecurityGroups'
```

---

## GCP — Connectivity Tests

GCP Connectivity Tests analyze the network path and evaluate firewall rules, routes, and forwarding rules.

```bash
# Create and run a connectivity test
gcloud network-management connectivity-tests create my-test \
  --source-instance=projects/my-project/zones/us-central1-a/instances/source-vm \
  --destination-instance=projects/my-project/zones/us-central1-a/instances/dest-vm \
  --protocol=TCP \
  --destination-port=443

# View results
gcloud network-management connectivity-tests describe my-test \
  --format="json(reachabilityDetails)"
```

### Firewall Rule Debugging
```bash
# Check which firewall rules apply to a specific instance
gcloud compute firewall-rules list \
  --filter="network=my-vpc" \
  --format="table(name,direction,allowed,sourceRanges,targetTags,priority)"

# Check which rules matched (via Firewall Insights)
# Console: Network Intelligence Center > Firewall Insights > Hit counts

# Test specific rule matching
gcloud compute instances describe my-instance --zone us-central1-a \
  --format="value(tags.items,networkInterfaces[0].subnetwork)"
# Cross-reference instance tags with firewall rule targets
```

---

## Common Misconfigurations

### 1. NSG Applied to Wrong Scope
NSG applied to the subnet but a NIC-level NSG overrides it (Azure evaluates NIC-level rules last for inbound traffic). Or NSG not associated with any subnet/NIC at all.
```bash
# Check NSG associations
az network nsg show --name MyNSG --resource-group MyRG \
  --query '{subnets:subnets[].id, nics:networkInterfaces[].id}'
```

### 2. Default Deny Forgotten
AWS custom NACLs default to deny all. If you create a custom NACL and attach it to a subnet without adding allow rules, all traffic is blocked.

### 3. Outbound Rules Blocking Return Traffic
Azure NSG outbound rules or GCP egress firewall rules blocking return traffic from a connection initiated by the VM itself. While NSGs/SGs are stateful, explicit deny rules can override connection tracking.

### 4. Service Tag / IP Range Stale
Azure service tags update automatically, but on-premises firewalls using hardcoded Azure IP ranges must be updated when Microsoft publishes new ranges (weekly JSON updates).

### 5. Priority Conflict
Higher-priority (lower number) deny rule matches before a lower-priority allow rule. Check effective rules to see evaluation order.

```bash
# Azure — find deny rules with lower priority than allow rules for same traffic
az network nsg rule list --nsg-name MyNSG --resource-group MyRG \
  --query "sort_by([?access=='Deny'], &priority)" -o table
```
**Analysis only — verify against vendor documentation before applying.**
