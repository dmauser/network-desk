---
name: netops-snat-egress
description: Read-only SNAT port exhaustion and egress health for public Standard Load Balancer (outbound rules and load-balancing-rule SNAT) and Azure NAT Gateway. Collects load balancer and NAT gateway configuration plus Azure Monitor metrics (UsedSnatPorts, AllocatedSnatPorts, SnatConnectionCount, VipAvailability, DipAvailability, NAT SNATConnectionCount, PacketDropCount, DatapathAvailability), then scores them deterministically with snat.py (per-backend SNAT utilization, failed SNAT connections, NAT packet drops, data path availability, default port allocation). Use for "SNAT exhaustion", "outbound connections failing", "intermittent timeouts to the internet", "NAT gateway drops", "egress latency".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): SNAT / port
exhaustion, outbound or egress failures, NAT gateway issues, intermittent outbound timeouts,
connection failures / resets, packet drops on the egress path, daily egress health task.

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read (`readonly_guard.classify_az_command` returns
`allow_read`). The agent never runs a write; findings carry human-run verification commands
only, with any change step commented out.

**Chain, don't guess.** Application-level latency or packet loss **without** SNAT signals
(utilization below the warning threshold, no failed SNAT connections, no NAT drops, availability
at 100%) is not an egress finding: hand off to `netops-routing-analyzer` (MTU, asymmetric
routing, forced tunnelling through an NVA / firewall, UDR next hop) and `netops-flow-insights`
(flow logs / Traffic Analytics for denied or dropped flows and top talkers).

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `load_balancers` | `az network lb list -g <rg> -o json` | `frontendIPConfigurations[].publicIPAddress`, `backendAddressPools[].backendIPConfigurations` / `loadBalancerBackendAddresses`, `outboundRules[].allocatedOutboundPorts` / `frontendIPConfigurations` / `backendAddressPool`, `loadBalancingRules[].disableOutboundSnat` |
| `nat_gateways` | `az network nat gateway list -g <rg> -o json` | `publicIpAddresses`, `publicIpPrefixes`, `idleTimeoutInMinutes`, `subnets` |
| `metrics` | `az monitor metrics list --resource <id> --metrics <name> --aggregation <agg> --interval PT1M --dimension <dims>` reduced to `{"resource_id","metric","value","aggregation","dimensions"}` | See the metric table below. For port/availability metrics put the **peak** (ports) or **minimum** (availability) per dimension combination in `value`; for counters put the window **Total** |
| `thresholds` | optional | `snat_warn_pct` (70), `snat_crit_pct` (85) — aligned with the scorecard; `failed_conn_crit` (1000); `min_allocated_ports` (1024) |

| Resource | Metric | Aggregation | Dimensions used |
| --- | --- | --- | --- |
| Load Balancer | `UsedSnatPorts`, `AllocatedSnatPorts` | Average (per backend instance) | `BackendIPAddress`, `FrontendIPAddress`, `ProtocolType` |
| Load Balancer | `SnatConnectionCount` | Total | `ConnectionState` (`Failed`), `BackendIPAddress` |
| Load Balancer | `VipAvailability` (data path), `DipAvailability` (health probe) | Average | `FrontendIPAddress`, `BackendIPAddress`, `BackendPort` |
| NAT Gateway | `SNATConnectionCount` | Total | `ConnectionState` (`Attempted` / `Failed`) |
| NAT Gateway | `PacketDropCount`, `TotalConnectionCount` | Total | — |
| NAT Gateway | `DatapathAvailability` | Average | — |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found". A public load balancer with
outbound or load-balancing rules but no `UsedSnatPorts` / `AllocatedSnatPorts` rows, or a NAT
gateway without `SNATConnectionCount`, is also reported as an evidence gap.

## Steps

1. Inventory in scope: `az network lb list -g <rg> -o json`,
   `az network lb outbound-rule list -g <rg> --lb-name <lb> -o json`,
   `az network nat gateway list -g <rg> -o json`.
2. Load Balancer SNAT metrics (incident window, or last 24 h for scheduled runs):
   `az monitor metrics list --resource <lb-id> --metrics UsedSnatPorts AllocatedSnatPorts --aggregation Average --interval PT1M --dimension BackendIPAddress -o json`,
   `az monitor metrics list --resource <lb-id> --metrics SnatConnectionCount --aggregation Total --interval PT1M --dimension ConnectionState BackendIPAddress -o json`,
   `az monitor metrics list --resource <lb-id> --metrics VipAvailability DipAvailability --aggregation Average --interval PT5M --dimension FrontendIPAddress -o json`.
3. NAT Gateway metrics (use Total / Average, not Count):
   `az monitor metrics list --resource <natgw-id> --metrics SNATConnectionCount --aggregation Total --interval PT1M --dimension ConnectionState -o json`,
   `az monitor metrics list --resource <natgw-id> --metrics PacketDropCount TotalConnectionCount --aggregation Total --interval PT1M -o json`,
   `az monitor metrics list --resource <natgw-id> --metrics DatapathAvailability --aggregation Average --interval PT5M -o json`.
4. Reduce each time series to one row per resource + metric + dimension combination
   (peak for SNAT ports, minimum for availability, sum for counters).
5. Save inputs with `netscope.save_netops_input`, then run
   `python snat.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_snat_egress_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `SNAT-LB-PORT-UTIL:<lb>:<backendIP>[:<fe>:<proto>]` | critical (>= `snat_crit_pct`), high (>= `snat_warn_pct`) | Peak UsedSnatPorts / AllocatedSnatPorts for a backend instance |
| `SNAT-LB-FAILED-CONN:<lb>:<backendIP>` | critical (>= `failed_conn_crit` in window), high (> 0) | `SnatConnectionCount` with `ConnectionState = Failed` |
| `SNAT-NAT-FAILED-CONN:<natgw>` | critical (>= `failed_conn_crit`), high (> 0) | NAT `SNATConnectionCount` Failed: SNAT exhaustion or connection limit |
| `SNAT-NAT-PACKET-DROPS:<natgw>` | high (with failed SNAT connections), medium | `PacketDropCount` > 0 (StandardV2: flow rate limit) |
| `SNAT-NAT-DATAPATHAVAILABILITY:<natgw>` | critical (0), high (< 100) | NAT gateway datapath availability |
| `SNAT-LB-VIPAVAILABILITY:<lb>[:<fe>]` | critical (0), high (< 100) | Load Balancer data path availability |
| `SNAT-LB-DIPAVAILABILITY:<lb>[:<fe>:<backend>:<port>]` | high (0), medium (< 100) | Health probe status |
| `SNAT-LB-DEFAULT-PORTS:<lb>:<rule>` | medium | Outbound rule `allocatedOutboundPorts = 0` (default port allocation) |
| `SNAT-LB-RULE-DEFAULT-SNAT:<lb>` | medium | Public LB without outbound rules; load-balancing rules with `disableOutboundSnat = false` |
| `SNAT-LB-LOW-PORTS:<lb>:<rule>` | low | Explicit allocation below `min_allocated_ports` |
| `SNAT-NAT-IDLE-TIMEOUT:<natgw>` | low | Idle timeout above 4 minutes on a NAT gateway that is failing or dropping |

Facts used (Learn): each public frontend IP provides 64,000 SNAT-eligible ports; default port
allocation per backend is 1,024 (1-50 instances), 512 (51-100), 256 (101-200), 128 (201-400),
64 (401-800), 32 (801-1,000), capped at 1,024 across frontends; each NAT gateway public IP
provides 64,512 SNAT ports, a NAT gateway takes up to 16 public IPs, supports 50,000
simultaneous connections per IP to a unique destination and up to 2 million in total, and has
a TCP idle timeout of 4-120 minutes (default 4).

Out of scope (not evaluated, no verifiable signal in these inputs): VMs relying on **default
outbound access** (needs subnet `defaultOutboundAccess` + NIC public IP inventory), and NAT
gateway total-connection saturation (limits differ by SKU) — `TotalConnectionCount` is carried
as evidence only.

## KPI definition

`snat_peak_util_pct` = highest `UsedSnatPorts / AllocatedSnatPorts x 100` across Load Balancer
backend instances in the window (rounded to 0.1). Scorecard grading (`scorecard.py`): good
<= 70, warning <= 85, critical above. Omitted when no LB SNAT port pairs were collected (the
scorecard shows "unknown"). NAT gateway health is reported through findings, not this KPI.

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Examples: `examples/snat-exhaustion-input.json` → `examples/snat-exhaustion-output.json`
(outbound rule backend at 97.8% with failed SNAT connections) and
`examples/natgw-drops-input.json` → `examples/natgw-drops-output.json` (NAT gateway failed
connections, packet drops, datapath availability dip, long idle timeout).

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Load Balancer,
Network Monitor and Network Troubleshooter specialists into `reference/` (see
`reference/INDEX.md`). Do not edit those files; they are rebuilt by
`node scripts/netops/build-netops.mjs`.

## Citations

- Load Balancer supported metrics (names, dimensions, aggregations): https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-loadbalancers-metrics
- NAT Gateway supported metrics: https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-natgateways-metrics
- Standard Load Balancer diagnostics (SNAT usage/allocation, ConnectionState = Failed alerting): https://learn.microsoft.com/azure/load-balancer/load-balancer-standard-diagnostics
- SNAT for outbound connections (64,000 ports per frontend IP, default port allocation table, `allocatedOutboundPorts = 0`): https://learn.microsoft.com/azure/load-balancer/load-balancer-outbound-connections
- Troubleshoot Load Balancer outbound connectivity: https://learn.microsoft.com/azure/load-balancer/troubleshoot-outbound-connection
- NAT Gateway metrics (failed connections, dropped packets, datapath availability): https://learn.microsoft.com/azure/nat-gateway/nat-metrics
- Troubleshoot NAT Gateway connectivity (50,000 / 2 million connections, idle timeout pressure): https://learn.microsoft.com/azure/nat-gateway/troubleshoot-nat-connectivity
- NAT Gateway resource (64,512 SNAT ports per public IP, idle timeout 4-120 min): https://learn.microsoft.com/azure/nat-gateway/nat-gateway-resource
- NAT Gateway overview (up to 16 public IPs): https://learn.microsoft.com/azure/nat-gateway/nat-overview
- Azure CLI: https://learn.microsoft.com/cli/azure/network/lb, https://learn.microsoft.com/cli/azure/network/lb/outbound-rule, https://learn.microsoft.com/cli/azure/network/nat/gateway, https://learn.microsoft.com/cli/azure/monitor/metrics

Analysis only — verify against vendor documentation before applying.
