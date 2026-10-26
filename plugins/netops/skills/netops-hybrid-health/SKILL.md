---
name: netops-hybrid-health
description: Read-only hybrid connectivity health for Azure VPN Gateway and ExpressRoute. Collects gateway, connection, tunnel, BGP peer, ExpressRoute circuit and route-summary state plus TunnelDiagnosticLog events and gateway metrics, then scores them deterministically with hybrid.py (tunnel down, BGP peer not Connected, flaps vs failover, traffic-selector mismatch drops, ER provisioning, BGP/ARP availability, private-peering prefix limit). Use for "VPN down", "tunnel flapping", "BGP not established", "ExpressRoute down", "on-prem unreachable".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): VPN / S2S /
IPsec / IKE tunnel down or flapping, BGP not established or missing learned routes,
ExpressRoute circuit or gateway down, "on-premises unreachable", daily hybrid health task.

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read or a documented read-equivalent diagnostic
(`readonly_guard.classify_az_command` returns `allow_read` / `allow_diagnostic`). The agent
never runs a write; findings carry human-run verification commands only.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `gateways` | `az network vnet-gateway list -g <rg>` | `gatewayType` `Vpn`/`ExpressRoute`, `enableBgp`, `activeActive` |
| `connections` | `az network vpn-connection list -g <rg>` / `show` | `connectionStatus`, `tunnelConnectionStatus[]`, `ingressBytesTransferred`, `egressBytesTransferred` |
| `bgp_peers` | `az network vnet-gateway list-bgp-peer-status -g <rg> -n <gw>` wrapped as `{"gateway_id", "value"}` | POST diagnostic (`getBgpPeerStatus/action`, custom NetOps role) |
| `er_circuits` | `az network express-route list` / `show` | `serviceProviderProvisioningState`, `circuitProvisioningState`, `sku.tier` |
| `er_route_summaries` | `az network express-route list-route-tables-summary -g <rg> -n <circuit> --peering-name AzurePrivatePeering --path primary` (and `secondary`) wrapped as `{"circuit_id","peering","path","value"}` | `statePfxRcd` is a prefix count, or a BGP state string when the session is down |
| `tunnel_events` | KQL below (Log Analytics `AzureDiagnostics`) | Needs gateway diagnostic settings to Log Analytics |
| `metrics` | `az monitor metrics list --resource <id> --metric <name> --aggregation <agg>` reduced to `{"resource_id","metric","value","dimensions"}` | `BgpPeerStatus` (Average), `TunnelEgressPacketDropTSMismatch` / `TunnelIngressPacketDropTSMismatch` (Total), ER `BgpAvailability` / `ArpAvailability` (Average) |
| `thresholds` | optional | `flap_events` (default 3), `er_route_warn_pct` (default 80) |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found".

### Fallback when POST diagnostics are blocked

`list-bgp-peer-status` is an async POST (202 then GET). If `RunAzCliReadCommands` rejects it
or the role lacks `getBgpPeerStatus/action`, collect the `BgpPeerStatus` metric instead
(`connected = 1, not connected = 0`; average below 1 means down for part of the window). The
engine uses it automatically for gateways missing from `bgp_peers` and records an evidence gap
only when neither source exists.

## Steps

1. Inventory in scope: `az network vnet-gateway list -g <rg> -o json`,
   `az network vpn-connection list -g <rg> -o json`, `az network express-route list -o json`.
2. For each BGP-enabled VPN gateway: `az network vnet-gateway list-bgp-peer-status -g <rg> -n <gw> -o json`
   (optional: `list-learned-routes`, `list-advertised-routes --peer <ip>` for route debugging).
3. For each ExpressRoute circuit: `az network express-route list-route-tables-summary` for
   `AzurePrivatePeering` on `primary` and `secondary`.
4. Metrics (last 24 h for scheduled runs, incident window otherwise):
   `az monitor metrics list --resource <gw-id> --metric BgpPeerStatus --aggregation Average --dimension BgpPeerAddress`,
   `... --metric TunnelEgressPacketDropTSMismatch --aggregation Total --dimension ConnectionName`,
   `az monitor metrics list --resource <circuit-id> --metric BgpAvailability --aggregation Average`.
5. Tunnel events with `execute_kusto_query`:

   ```kusto
   AzureDiagnostics
   | where TimeGenerated > ago(24h)
   | where Category == "TunnelDiagnosticLog"
   | where OperationName in ("TunnelConnected", "TunnelDisconnected")
   | project TimeGenerated, OperationName, Resource, ResourceId, remoteIP_s, instance_s
   | order by TimeGenerated asc
   ```

   Related categories for root cause: `IKEDiagnosticLog` (IKE negotiation),
   `RouteDiagnosticLog` (`BgpConnectedEvent`, `BgpDisconnectedEvent`, `BgpRouteUpdate`),
   `GatewayDiagnosticLog` (`HostMaintenanceEvent`, `GatewayTenantPrimaryChanged`).
   Policy-based gateways emit only Gateway and Route logs.
6. Save inputs with `netscope.save_netops_input`, then run
   `python hybrid.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_hybrid_health_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `HYB-CONN-NOT-CONNECTED:<conn>` | critical (NotConnected/Unknown), high (Connecting) | Connection is not `Connected` |
| `HYB-TUNNEL-DEGRADED:<conn>:<tunnel>` | medium | Connection up but one tunnel instance down (redundancy lost) |
| `HYB-TUNNEL-NO-TRAFFIC:<conn>` | low | Connected IPsec connection with 0 bytes in and out |
| `HYB-BGP-NOT-CONNECTED:<gw>:<peer>` | critical / high | Peer `state` not `Connected`, or `BgpPeerStatus` average below 1 |
| `HYB-TUNNEL-FLAP:<gw>:<remoteIP>` | high / medium | `flap_events`+ disconnects or still down; pattern classifies failover vs same-instance |
| `HYB-TS-MISMATCH:<gw>:<conn>:<metric>` | high | Traffic-selector mismatch packet drops |
| `HYB-ER-NOT-PROVISIONED:<circuit>` / `HYB-ER-CIRCUIT-DISABLED:<circuit>` | critical | Provider state not `Provisioned` / circuit not `Enabled` |
| `HYB-ER-BGPAVAILABILITY:…` / `HYB-ER-ARPAVAILABILITY:…` | critical (0%) / high | MSEE BGP or ARP availability below 100% |
| `HYB-ER-BGP-DOWN:<circuit>:<peering>:<path>:<neighbor>` | critical | `statePfxRcd` is a state (for example `Idle`), not a count |
| `HYB-ER-ROUTE-LIMIT:…` | high (>= warn %) / critical (>= limit) | Private peering prefixes near 4,000 (10,000 Premium) |

Flap classification (from the VPN diagnostics guide): disconnect on one instance followed by
connect on the **other** instance = failover / maintenance; disconnect and reconnect on the
**same** instance = DPD timeout, network glitch or on-premises device; disconnect with no
reconnect = tunnel still down (SC-01 / SC-02 pattern).

A healthy control plane (tunnel and BGP `Connected`) with traffic still failing is **not** a
hybrid-health finding; hand off to `netops-routing-analyzer` (UDR black hole, IP forwarding on
the NVA) — see SC-03 / SC-07 in `evals/netops`.

KPIs: `tunnels_connected_pct`, `bgp_peers_connected_pct` (consumed by the KPI scorecard).

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Example: `examples/sc01-vpn-down-input.json` → `examples/sc01-vpn-down-output.json`.

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Hybrid Connectivity
specialist into `reference/` (see `reference/INDEX.md`). Do not edit those files; they are
rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- BGP peer status API (fields, `state` enum): https://learn.microsoft.com/rest/api/network-gateway/virtual-network-gateways/get-bgp-peer-status
- Troubleshoot BGP on VPN Gateway (BgpPeerStatus 1/0, alert < 1): https://learn.microsoft.com/troubleshoot/azure/vpn-gateway/vpn-gateway-troubleshoot-bgp
- VPN Gateway diagnostic logs and flap interpretation: https://learn.microsoft.com/azure/vpn-gateway/troubleshoot-vpn-with-azure-diagnostics
- VPN Gateway monitoring reference (metrics, log categories): https://learn.microsoft.com/azure/vpn-gateway/monitor-vpn-gateway-reference
- Virtual network gateway supported metrics: https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-virtualnetworkgateways-metrics
- ExpressRoute circuit provisioning states: https://learn.microsoft.com/azure/expressroute/expressroute-workflows
- ExpressRoute route summary API (`statePfxRcd`): https://learn.microsoft.com/rest/api/expressroute/express-route-circuits/list-routes-table-summary
- ExpressRoute monitoring reference (BgpAvailability, ArpAvailability): https://learn.microsoft.com/azure/expressroute/monitor-expressroute-reference
- ExpressRoute prefix limits: https://learn.microsoft.com/azure/expressroute/expressroute-faqs and https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-networking-limits
- Azure CLI: https://learn.microsoft.com/cli/azure/network/vnet-gateway, https://learn.microsoft.com/cli/azure/network/vpn-connection, https://learn.microsoft.com/cli/azure/network/express-route

Analysis only — verify against vendor documentation before applying.
