---
name: netops-ip-capacity
description: Read-only IP and gateway capacity analysis for Azure virtual networks. Collects VNets, per-subnet IP usage (VirtualNetworks List Usage), optional usage history and gateway metrics, then scores them deterministically with capacity.py (subnet utilization vs warn/critical thresholds, least-squares exhaustion forecast, undersized GatewaySubnet / AzureFirewallSubnet / AzureBastionSubnet, VNet address space with no room for new subnets, ExpressRoute gateway CPU and VPN gateway throughput against operator limits). Use for "subnet is full", "IP address exhaustion", "no available IPs", "capacity forecast", "address space headroom".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): subnet full,
IP address exhaustion, "no available IPs" when scaling or creating private endpoints,
address-space or capacity headroom questions, forecasting, weekly capacity task.

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read (`readonly_guard.classify_az_command` returns
`allow_read`). The agent never runs a write; findings carry human-run verification commands and
commented change steps only.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `vnets` | `az network vnet list -o json` | `addressSpace.addressPrefixes`, `subnets[].addressPrefix` / `addressPrefixes`, `delegations` |
| `usages` | `az rest --method get --url "https://management.azure.com/<vnet-id>/usages?api-version=2026-01-01"` wrapped as `{"vnet_id", "value"}` | Per subnet: `id` (subnet id), `currentValue` (IPs used), `limit` (subnet size), `name.value` `SubnetSpace`, `unit` `Count`. Rows with `limit <= 0` (for example `GatewaySubnet` returns `-1`) are skipped with a warning |
| `history` | earlier `usages` snapshots reduced to `{"subnet_id", "as_of", "used"}` | Optional; at least one earlier point per subnet to forecast |
| `as_of` | date (`YYYY-MM-DD`) the `usages` were collected | Required to forecast; the engine never reads the clock |
| `gateway_metrics` | `az monitor metrics list --resource <gw-id> --metric <name> --aggregation Average` reduced to `{"resource_id","metric","value","limit","dimensions"}` | `ExpressRouteGatewayCpuUtilization` / `ScalableExpressRouteGatewayCpuUtilization` (percent); `AverageBandwidth`, `TunnelAverageBandwidth`, `P2SConnectionCount`, `ExpressRouteGatewayBitsPerSecond`, `ExpressRouteGatewayCountOfRoutesLearnedFromPeer` only when you supply `limit` |
| `thresholds` | optional | `subnet_warn_pct` 80, `subnet_crit_pct` 95, `forecast_days` 90, `vnet_min_free_prefix` 29, `gateway_cpu_pct` 80, `gateway_util_pct` 80 |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found". VNets present in `vnets` but
missing from `usages` are reported as a gap too.

`az network vnet list-usage` is not in the current Azure CLI reference for `az network vnet`, so
collect usage with the documented REST operation (`az rest --method get`, a read).

## Steps

1. Inventory in scope: `az network vnet list -o json` (or per resource group
   `az network vnet list -g <rg> -o json`).
2. For each VNet:
   `az rest --method get --url "https://management.azure.com/<vnet-id>/usages?api-version=2026-01-01" -o json`
   and wrap the `value` array as `{"vnet_id": "<vnet-id>", "value": [...]}`. Optional detail per
   subnet: `az network vnet subnet list -g <rg> --vnet-name <vnet> -o json`.
3. History (optional): reuse the `usages` saved by previous scheduled runs
   (`netscope.save_netops_input`); each subnet needs `{"subnet_id","as_of","used"}` points.
4. Gateway capacity (optional): `az network vnet-gateway list -g <rg> -o json`, then
   `az monitor metrics list --resource <gw-id> --metric ExpressRouteGatewayCpuUtilization --aggregation Average --interval PT5M -o json`
   and, for VPN gateways, `... --metric TunnelAverageBandwidth --aggregation Average --interval PT5M -o json`
   (set `limit` to the SKU aggregate throughput benchmark you accept as capacity; it is a
   benchmark, not a hard limit).
5. Save inputs with `netscope.save_netops_input`, then run
   `python capacity.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_ip_capacity_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `CAP-SUBNET-UTIL:<vnet>:<subnet>` | critical (>= `subnet_crit_pct`), high (>= `subnet_warn_pct`) | `currentValue / limit` at or above threshold; new NICs / private endpoints / scale-out will fail when full |
| `CAP-SUBNET-FORECAST:<vnet>:<subnet>` | medium | Least-squares linear fit of `history` + current usage reaches `limit` within `forecast_days`; evidence has the projected date |
| `CAP-SPECIAL-SUBNET-UNDERSIZED:<vnet>:<subnet>` | medium | `GatewaySubnet` smaller than /27 (/29 is Basic SKU only), `AzureFirewallSubnet` smaller than /26, `AzureBastionSubnet` smaller than /26 |
| `CAP-VNET-SPACE-FULL:<vnet>` | low | No unallocated block of `/vnet_min_free_prefix` (default /29, the smallest IPv4 subnet) left in the address space |
| `CAP-GW-METRIC:<gw>:<metric>[:<dims>]` | high | ER gateway CPU >= `gateway_cpu_pct`, or a throughput/count metric >= `gateway_util_pct` of the supplied `limit` |

Azure reserves 5 IP addresses in every subnet; the usage `limit` is the subnet size as returned
by the API. Subnets that are full typically surface as allocation failures when creating NICs,
private endpoints or scaling VM scale sets / AKS node pools — confirm with this skill before
redesigning addressing.

KPI: `subnets_over_threshold` = number of in-scope subnets with utilization >= `subnet_warn_pct`
(scorecard: good <= 0, warning <= 2). Emitted only when `usages` were collected.

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Example: `examples/subnet-exhaustion-input.json` → `examples/subnet-exhaustion-output.json`.

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Network Capacity Planning and
VNet/Subnet Architect specialists into `reference/` (see [reference/INDEX.md](reference/INDEX.md)). Do
not edit those files; they are rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- Virtual Networks - List Usage (currentValue, limit, id, SubnetSpace): https://learn.microsoft.com/rest/api/virtualnetwork/virtual-networks/list-usage
- Virtual network FAQ (5 reserved IPs per subnet, /29 smallest IPv4 subnet): https://learn.microsoft.com/azure/virtual-network/virtual-networks-faq
- Azure CLI `az network vnet` / `az network vnet subnet`: https://learn.microsoft.com/cli/azure/network/vnet and https://learn.microsoft.com/cli/azure/network/vnet/subnet
- GatewaySubnet size (/27 or larger; /29 Basic only): https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-about-vpn-gateway-settings
- AzureFirewallSubnet /26: https://learn.microsoft.com/azure/firewall/firewall-faq
- AzureBastionSubnet /26 or larger: https://learn.microsoft.com/azure/bastion/configuration-settings
- Virtual network gateway supported metrics: https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-virtualnetworkgateways-metrics
- ExpressRoute gateway metrics: https://learn.microsoft.com/azure/expressroute/expressroute-monitoring-metrics-alerts
- VPN Gateway SKUs (aggregate throughput benchmark): https://learn.microsoft.com/azure/vpn-gateway/about-gateway-skus

Analysis only — verify against vendor documentation before applying.
