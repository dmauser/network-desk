# Skill: Network Migration Planner

## Purpose

This skill provides structured guidance for planning network migrations: on-premises to cloud, cloud to cloud, and legacy-to-modern network transitions. It covers address space strategies (re-IP vs NAT vs overlap), phased migration approaches, DNS cutover, traffic shifting, rollback planning, and common pitfalls.

## Core Knowledge

### Migration Scenarios

#### Scenario 1: On-Premises to Cloud

The most common migration. Key challenge: on-prem address space often conflicts with planned cloud ranges, and hybrid connectivity (VPN/ExpressRoute) must coexist during the transition period.

**Address space strategies:**

| Strategy | When to Use | Pros | Cons |
|----------|------------|------|------|
| **Re-IP** | Greenfield cloud, no CIDR overlap possible | Clean address plan, no NAT complexity | Requires updating all DNS records, firewall rules, application configs with hardcoded IPs |
| **NAT** | CIDRs overlap and re-IP is impractical | Minimal workload disruption | NAT complexity, double-NAT scenarios, breaks some protocols (SIP, FTP active mode) |
| **Parallel (non-overlapping)** | Sufficient RFC 1918 space available | Simplest — both networks coexist natively | Requires unused address space |

**Re-IP workflow:**
```
1. Inventory all IPs in use (servers, appliances, DNS records, firewall rules, app configs)
2. Assign new cloud CIDRs (ensure no overlap with retained on-prem ranges)
3. Update DNS records to point to new IPs (use low TTLs during cutover)
4. Update firewall rules and ACLs on both sides
5. Migrate workloads with new IPs
6. Validate connectivity and application behavior
7. Decommission old on-prem IPs after validation period
```

**NAT workflow (Azure):**
```bash
# Create NAT Gateway for outbound
az network nat gateway create \
  --name migration-nat \
  --resource-group rg-migration \
  --public-ip-addresses pip-nat \
  --idle-timeout 10

# Associate with subnet
az network vnet subnet update \
  --resource-group rg-migration \
  --vnet-name migration-vnet \
  --name workload-subnet \
  --nat-gateway migration-nat
```

#### Scenario 2: Cloud-to-Cloud Migration

Moving workloads between cloud providers (e.g., AWS to Azure) or between regions within the same provider.

**Parallel network approach:**
1. Build the target cloud network alongside the source (no overlap)
2. Establish cross-cloud connectivity (VPN between Azure VNet and AWS VPC)
3. Migrate workloads in waves, shifting DNS to new IPs
4. Decommission source network after validation

```bash
# Cross-cloud VPN: Azure side
az network vnet-gateway create \
  --name azure-vpn-gw \
  --resource-group rg-migration \
  --vnet migration-vnet \
  --gateway-type Vpn \
  --vpn-type RouteBased \
  --sku VpnGw2

az network local-gateway create \
  --name aws-local-gw \
  --resource-group rg-migration \
  --gateway-ip-address <AWS_VPN_ENDPOINT_IP> \
  --local-address-prefixes 10.1.0.0/16    # AWS VPC CIDR

az network vpn-connection create \
  --name azure-to-aws \
  --resource-group rg-migration \
  --vnet-gateway1 azure-vpn-gw \
  --local-gateway2 aws-local-gw \
  --shared-key <PSK>
```

### Phased Migration Approach

Follow this five-phase methodology for any network migration:

#### Phase 1: Assess (1–2 weeks)

- **Inventory current state:** All networks, subnets, routes, peerings, VPN tunnels, firewall rules, DNS records, IP assignments.
- **Map dependencies:** Which applications talk to which? What IP addresses are hardcoded? What DNS names resolve to migrating IPs?
- **Identify constraints:** Compliance requirements (data residency), SLA requirements (maximum downtime), bandwidth limitations.
- **Document baseline metrics:** Latency between tiers, throughput, packet loss. These become validation criteria post-migration.

```bash
# Azure: export current network topology
az network vnet list -o json > vnet-inventory.json
az network route-table list -o json > route-tables.json
az network nsg list -o json > nsg-rules.json

# AWS: export VPC topology
aws ec2 describe-vpcs --output json > vpc-inventory.json
aws ec2 describe-route-tables --output json > route-tables.json
aws ec2 describe-security-groups --output json > security-groups.json
```

#### Phase 2: Plan (1–2 weeks)

- **Design target network:** Use the Address Planner and Hub-Spoke Design skills to create the target topology.
- **Plan connectivity bridge:** VPN or peering between source and target networks for the migration period.
- **Define migration waves:** Group workloads by dependency. Migrate in order: infrastructure services → stateless app tiers → stateful data tiers.
- **Plan DNS cutover strategy:** Lower TTLs 48 hours before migration. Prepare DNS record updates. Consider split-horizon DNS during transition.
- **Document rollback triggers:** Define conditions that trigger rollback (e.g., >5% error rate, latency >2x baseline, data sync failures).

#### Phase 3: Pilot (1 week)

- **Migrate a non-critical workload** end-to-end using the planned process.
- **Validate:** Connectivity, DNS resolution, firewall rules, latency, application behavior.
- **Refine:** Update the migration plan based on pilot findings.
- **Benchmark:** Compare performance metrics against Phase 1 baseline.

#### Phase 4: Migrate (varies)

- **Execute migration waves** per the plan.
- **Per-wave steps:**
  1. Pre-flight: verify target subnet, NSG/security groups, route tables are in place.
  2. Migrate: move compute, re-point DNS, update firewall rules.
  3. Validate: test application connectivity, check monitoring dashboards, run smoke tests.
  4. Stabilize: monitor for 24–48 hours before proceeding to next wave.

#### Phase 5: Validate and Decommission (1–2 weeks)

- **Full regression testing** on the target network.
- **Remove connectivity bridge** (VPN between source and target).
- **Decommission source network resources** (VNets, VPCs, gateways, firewall rules).
- **Restore DNS TTLs** to normal values.
- **Update documentation:** Network diagrams, IP address plans, runbooks.

### Rollback Strategy

Every migration must have a rollback plan. Key components:

1. **Point of no return:** Define the point after which rollback is more disruptive than pushing forward (typically after data tier migration and DNS propagation).
2. **DNS rollback:** Revert DNS records to original IPs. Effective within TTL window.
3. **Traffic rollback:** If using a load balancer or traffic manager, shift traffic back to source.
4. **Data rollback:** If databases were migrated, ensure replication is still active to the source until the validation window closes.

```bash
# Azure Traffic Manager for gradual traffic shifting
az network traffic-manager endpoint update \
  --resource-group rg-tm \
  --profile-name migration-tm \
  --name source-endpoint \
  --type externalEndpoints \
  --weight 100    # shift back to source

az network traffic-manager endpoint update \
  --resource-group rg-tm \
  --profile-name migration-tm \
  --name target-endpoint \
  --type externalEndpoints \
  --weight 0      # stop sending to target
```

### Common Pitfalls

| Pitfall | Impact | Prevention |
|---------|--------|------------|
| **DNS propagation delays** | Users hit old IPs after migration, causing errors | Lower TTLs 48h before migration. Monitor DNS resolution from multiple locations. Use `dig` / `nslookup` to verify propagation. |
| **Asymmetric routing during cutover** | Outbound packets take new path, return packets take old path, stateful firewalls drop the return | Ensure symmetric routing by updating route tables on BOTH sides simultaneously. In Azure, check effective routes: `az network nic show-effective-route-table`. |
| **Firewall rule gaps** | New network ranges not permitted in existing firewall rules | Audit all firewall rules pre-migration. Add target CIDRs to allow lists BEFORE migrating. Remove source CIDRs AFTER validation. |
| **Hardcoded IPs in application configs** | Applications break when IPs change | Scan codebases and configs for IP references. Replace with DNS names or service discovery before migration. Use `grep -rn "10\.\|172\.16\.\|192\.168\." /app/config/` to find candidates. |
| **MTU mismatches** | VPN tunnels reduce MTU (typically 1400 vs 1500). Large packets dropped silently. | Set TCP MSS clamping on VPN gateways. Test with `ping -M do -s 1472 <target>` to validate path MTU. |
| **Certificate/TLS issues** | Certificates bound to old IPs or hostnames fail after migration | Use SAN certificates with both old and new names. Add new DNS names to certificates before cutover. |

### Migration Checklist Template

```markdown
## Pre-Migration
- [ ] IP address plan finalized and validated (no overlaps)
- [ ] Target VNet/VPC and subnets created
- [ ] NSGs / Security Groups configured
- [ ] Route tables and UDRs in place
- [ ] Connectivity bridge (VPN/peering) established and tested
- [ ] DNS TTLs lowered (48h before cutover)
- [ ] Firewall rules updated to allow target CIDRs
- [ ] Rollback plan documented and reviewed

## During Migration
- [ ] Workload migrated / redeployed
- [ ] DNS records updated to new IPs
- [ ] Connectivity validated (ping, traceroute, app-level health checks)
- [ ] Monitoring dashboards confirm no anomalies

## Post-Migration
- [ ] 24–48h stability monitoring complete
- [ ] Performance metrics match or exceed baseline
- [ ] Connectivity bridge removed
- [ ] Source resources decommissioned
- [ ] DNS TTLs restored to normal
- [ ] Documentation updated
```

## References

- Azure migration guide: https://learn.microsoft.com/azure/cloud-adoption-framework/migrate/
- AWS migration strategies: https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html
- GCP migration center: https://cloud.google.com/migration-center/docs/overview
- Azure Traffic Manager: https://learn.microsoft.com/azure/traffic-manager/traffic-manager-overview

**Analysis only — verify against vendor documentation before applying.**
