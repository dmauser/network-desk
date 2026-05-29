# Skill: Network Cost Optimization (`price_skill_cost_optimizer`)

Strategies and checklists for reducing cloud networking costs. Covers egress reduction, right-sizing, reserved capacity, architecture patterns, and identifying unused resources.

---

## 1. Reduce Egress Costs

Egress is typically the largest and most surprising networking cost. Key strategies:

### CDN Offload for Static Content

Move static assets (images, JS, CSS, videos, downloads) to a CDN. CDN egress is 25-50% cheaper than origin egress, and it reduces load on your origin infrastructure.

| Approach | Cost Impact |
|---|---|
| Serve static content from origin | Full egress rate ($0.087-$0.12/GB) |
| Serve via CDN | $0.06-$0.085/GB + cache fill |
| Estimated savings | 25-50% on static content egress |

```bash
# Azure — check which content could be CDN-cached
az cdn endpoint show --name <endpoint> -g <rg> --profile-name <profile> \
  --query '{origins:origins[].hostName, caching:deliveryPolicy}'

# AWS — check CloudFront cache hit ratio
aws cloudwatch get-metric-statistics --namespace AWS/CloudFront \
  --metric-name CacheHitRate --dimensions Name=DistributionId,Value=<id> \
  --period 86400 --statistics Average --start-time 2024-01-01 --end-time 2024-02-01
```

### Enable Compression

Compressing API responses and web content reduces egress volume by 60-80%:

```bash
# Check if compression is enabled on Azure Application Gateway
az network application-gateway show --name <appgw> -g <rg> \
  --query 'httpListeners[].{name:name, protocol:protocol}'

# Verify compression in response headers
curl -s -D- -o /dev/null -H "Accept-Encoding: gzip" https://your-api.com/endpoint \
  | grep -i content-encoding
```

### Keep Traffic Intra-Region

Cross-region traffic costs $0.02-$0.08/GB. Architect for data locality:

- Deploy read replicas in the same region as consumers
- Use region-local caches (Redis, Memcached)
- Avoid cross-region database queries — replicate data instead
- Place compute close to storage

### Private Endpoints vs. Internet Egress

Traffic to PaaS services (Storage, SQL, Key Vault) through service endpoints or private endpoints stays on the Microsoft/AWS/Google backbone and avoids internet egress charges:

| Path | Egress Cost |
|---|---|
| Via public endpoint (internet) | Full egress rate |
| Via service endpoint | Free (Azure) |
| Via private endpoint | ~$0.01/GB data processing (Azure) |
| Via VPC endpoint (AWS) | $0.01/GB data processing |

---

## 2. Right-Size Gateways and Resources

Over-provisioned gateways waste hundreds of dollars monthly.

### VPN Gateway Right-Sizing

```bash
# Azure — check VPN gateway bandwidth utilization
az monitor metrics list --resource <vpn-gw-id> \
  --metric "AverageBandwidth" --interval PT1H --aggregation Average

# If average bandwidth is <30% of SKU capacity, consider downgrading:
# VpnGw3AZ ($1,000/mo, 1.25 Gbps) → VpnGw2AZ ($518/mo, 1 Gbps)
# VpnGw2AZ ($518/mo, 1 Gbps) → VpnGw1AZ ($263/mo, 650 Mbps)
```

### ExpressRoute Circuit Right-Sizing

```bash
# Check ER circuit utilization
az network express-route stats show --name <circuit> -g <rg>

# If utilization consistently <25% of circuit speed, consider downsizing
# ER 1 Gbps ($1,100/mo) → ER 500 Mbps ($550/mo) saves $6,600/year
```

### Load Balancer Right-Sizing

```bash
# Azure — check Application Gateway capacity units
az monitor metrics list --resource <appgw-id> \
  --metric "CapacityUnits" --interval PT1H --aggregation Average

# AWS — check ALB consumed LCUs
aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name ConsumedLCUs --dimensions Name=LoadBalancer,Value=<arn-suffix> \
  --period 86400 --statistics Maximum --start-time 2024-01-01 --end-time 2024-02-01
```

---

## 3. Reserved Capacity and Commitment Discounts

### Azure ExpressRoute Reserved Circuits

Committing to 1-year or 3-year terms saves 15-30%:

| Circuit Speed | Pay-as-you-go ($/month) | 1-Year Reserved | 3-Year Reserved |
|---|---|---|---|
| 1 Gbps Unlimited | ~$1,650 | ~$1,400 (15% off) | ~$1,150 (30% off) |
| 10 Gbps Unlimited | ~$6,550 | ~$5,570 (15% off) | ~$4,585 (30% off) |

### AWS Direct Connect Capacity Reservations

AWS offers committed-use pricing for Direct Connect ports through AWS Savings Plans and enterprise discounts. Contact AWS for custom pricing on long-term commitments.

### Azure Savings Plans

Azure savings plans for compute can reduce NVA (VM-based firewall) costs by up to 72% for 3-year commitments.

---

## 4. Architecture Patterns That Save Money

### NAT Gateway vs. Load Balancer SNAT

> **Pricing assumption reviewed 2026-05-29:** NAT gateway rates change frequently. Use the provider calculators/pricing pages for exact numbers; examples here are illustrative only.

| Approach | Cost model | Notes |
|---|---|---|
| Azure NAT Gateway | Gateway uptime + data processing + public IP resources | Best for managed outbound at scale; verify Standard vs StandardV2 needs |
| AWS NAT Gateway | Gateway uptime + data processing + public IPv4 charges + egress | Avoid sending AWS-service traffic through NAT when Gateway/Interface Endpoints exist |
| GCP Cloud NAT | Gateway uptime + data processing + public IP hourly charges + egress | Do not model as data-processing-only; see https://cloud.google.com/nat/pricing |
| LB SNAT / existing egress path | Often lower incremental cost if already deployed | Limited port count, operational constraints, and cloud-specific support |
| Instance-level public IPs | Public IP hourly/monthly charges + exposure risk | Simple but increases attack surface |

> **Recommendation:** If you already have a supported load balancer or private endpoint path, evaluate it before adding a NAT Gateway. NAT data processing and public IP charges can dominate outbound-heavy workloads.

### Hub-Spoke vs. Flat Network

Hub-spoke with centralized firewalling means all inter-spoke traffic traverses the hub firewall:

| Pattern | Firewall Data Processing | Peering Cost |
|---|---|---|
| Hub-spoke (all via FW) | High — all inter-spoke GB | 2× peering hops |
| Direct spoke-to-spoke peering | Lower — only inspected traffic | 1× peering hop |
| vWAN with routing intent | High — all via secured hub | vWAN hub charges |

If inter-spoke traffic doesn't require inspection, direct peering saves both firewall data processing and peering transit costs.

### Private Endpoints — Watch the Data Processing Cost

| Component | Cost |
|---|---|
| Private endpoint (resource) | $0.01/hr (~$7.30/month) |
| Data processing | $0.01/GB inbound + $0.01/GB outbound |

For high-throughput scenarios (e.g., 10 TB/month to Storage), the $200/month data processing cost is still far less than internet egress ($870/month at $0.087/GB), but it's not zero.

---

## 5. Identify and Remove Unused Resources

### Idle VPN Gateways

```bash
# Azure — find VPN gateways with no connections
az network vnet-gateway list -g <rg> --query "[?length(ipConfigurations) > \`0\`].{name:name, sku:sku.name}" -o table

# Check for zero-traffic gateways
az network vpn-connection list -g <rg> --query "[].{name:name, status:connectionStatus, bytesIn:ingressBytesTransferred}"
```

### Unused Public IPs

```bash
# Azure — find unattached public IPs (charged at ~$3.60/month each)
az network public-ip list -g <rg> --query "[?ipConfiguration==null].{name:name, ip:ipAddress, sku:sku.name}" -o table

# AWS — find unattached Elastic IPs (charged at $0.005/hr = $3.65/month)
aws ec2 describe-addresses --query 'Addresses[?AssociationId==null].{IP:PublicIp,AllocationId:AllocationId}'
```

### Orphaned Load Balancers

```bash
# Azure — LBs with no backend pools
az network lb list -g <rg> --query "[?length(backendAddressPools) == \`0\`].{name:name, sku:sku.name}"

# AWS — ALBs with no registered targets
aws elbv2 describe-target-health --target-group-arn <arn> --query 'TargetHealthDescriptions'
```

### Unused ExpressRoute Circuits

```bash
# Azure — check if ER circuit is provisioned but unused
az network express-route list -g <rg> \
  --query "[].{name:name, state:circuitProvisioningState, serviceProviderState:serviceProviderProvisioningState, bandwidth:bandwidthInMbps}"
```

---

## Optimization Checklist

Run through this checklist quarterly:

| # | Check | CLI / Action | Est. Savings |
|---|---|---|---|
| 1 | Delete unused public IPs | `az network public-ip list --query "[?ipConfiguration==null]"` | $3.60/IP/month |
| 2 | Remove idle VPN gateways | Check connection count and traffic | $27–$2,400/month per GW |
| 3 | Downsize over-provisioned VPN GWs | Check avg bandwidth vs SKU capacity | 30-60% of GW cost |
| 4 | Downsize ExpressRoute circuits | Check utilization vs provisioned speed | $550+/month |
| 5 | Enable CDN for static content | Set up Azure CDN / CloudFront / Cloud CDN | 25-50% egress savings |
| 6 | Enable compression on APIs | App Gateway / ALB / origin config | 60-80% egress reduction |
| 7 | Use Private Endpoints for PaaS | Replace internet access to Storage/SQL | Avoids egress charges |
| 8 | Clean up orphaned LBs | Check for LBs with no backends | $18+/month per LB |
| 9 | Consider reserved circuits | Compare PAYG vs 1yr/3yr ER pricing | 15-30% savings |
| 10 | Review inter-region traffic | Check if replicas can be moved closer | $0.02-$0.08/GB saved |
| 11 | Check NAT Gateway cost model | Review gateway uptime, data processing, public IPs, and egress | Significant at scale; verify current rates |
| 12 | Audit firewall data processing | Right-size or consider NVA at high volume | Variable |

---

## Cost Monitoring Setup

### Azure Cost Alerts

```bash
# Create a budget with alert at 80% and 100%
az consumption budget create --budget-name "NetworkCosts" \
  --amount 5000 --time-grain Monthly --category Cost \
  --resource-group <rg> --start-date 2024-01-01 --end-date 2025-01-01
```

### AWS Cost Anomaly Detection

```bash
# Create cost anomaly monitor for networking
aws ce create-anomaly-monitor --anomaly-monitor '{
  "MonitorName": "NetworkCostMonitor",
  "MonitorType": "DIMENSIONAL",
  "MonitorDimension": "SERVICE"
}'
```

Pricing is indicative — verify against current vendor pricing pages before budgeting.
**Analysis only — verify against vendor documentation before applying.**
