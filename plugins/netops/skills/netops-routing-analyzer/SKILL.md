---
name: netops-routing-analyzer
description: Read-only routing analysis for Azure virtual networks. Collects route tables (UDRs), NIC effective routes, VNet peerings, NVA network interfaces, optional Network Watcher next-hop results and data-plane probe evidence, then analyzes them deterministically with routing.py — UDR black holes (next hop None), peering not Connected / access or forwarded traffic disabled / not in sync, asymmetric routing through an NVA or Azure Firewall, NVA NICs with IP forwarding off, NVA paths that fail while the control plane is healthy (guest OS forwarding), and MTU/MSS black holes (small requests succeed, large responses hang). Use for "traffic black-holed", "UDR / route table", "effective routes", "next hop", "asymmetric routing through the NVA", "peering broken", "large responses hang". Fallback skill for unclassified connectivity symptoms.
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`; this is also the
`fallbackSkill`): UDR / route table / effective routes / next hop questions, black-holed
traffic, asymmetric routing or return-path problems through an NVA or Azure Firewall, forced
tunneling, hub-spoke / spoke-to-spoke / transit or peering problems, "every monitor is green
but large responses hang".

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read or a documented read-equivalent diagnostic
(`readonly_guard.classify_az_command` returns `allow_read` / `allow_diagnostic`). The agent
never runs a write; findings carry human-run verification commands, and any change command is
commented out for human review. `az network watcher test-connectivity` is **not** used (the
guard denies it: `connectivityCheck/action` can deploy the Network Watcher agent extension).

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `route_tables` | `az network route-table list -g <rg> -o json` | `routes[]` → `addressPrefix`, `nextHopType` (`VirtualNetworkGateway`, `VnetLocal`, `Internet`, `VirtualAppliance`, `None`), `nextHopIpAddress`; `subnets[].id` |
| `effective_routes` | `az network nic show-effective-route-table -g <rg> -n <nic> -o json` wrapped as `{"nic_id", "value"}` | POST diagnostic (`networkInterfaces/effectiveRouteTable/action`, custom NetOps role). `addressPrefix[]`, `nextHopType`, `nextHopIpAddress[]`, `source` (`Default`/`User`/`VirtualNetworkGateway`), `state` (`Active`/`Invalid`) |
| `vnet_peerings` | `az network vnet peering list -g <rg> --vnet-name <vnet> -o json` wrapped as `{"vnet_id", "value"}` | Collect **both** sides. `peeringState` (`Initiated`, `Connected`, `Disconnected`), `peeringSyncLevel` (`FullyInSync`, `RemoteNotInSync`, `LocalNotInSync`, `LocalAndRemoteNotInSync`), `allowVirtualNetworkAccess`, `allowForwardedTraffic`, `allowGatewayTransit`, `useRemoteGateways`, `remoteVirtualNetwork.id`, `remoteAddressSpace` / `remoteVirtualNetworkAddressSpace` |
| `nics` | `az network nic list -g <rg> -o json` | `enableIPForwarding`, `ipConfigurations[].privateIPAddress` (maps NVA next hop IPs to NICs) |
| `next_hop_checks` | optional: `az network watcher show-next-hop -g <rg> --vm <vm> --source-ip <ip> --dest-ip <ip> -o json` plus `{"vm_id","source_ip","dest_ip"}` | `nextHopType`, `nextHopIpAddress`, `routeTableId` (the string `System Route` when no user route applies) |
| `flows` | optional operator input | `{"name","source_nic_id","destination_ip","return_nic_id","source_ip"}`: the engine does a longest-prefix match on both NICs' effective routes to compare forward vs return next hops |
| `path_checks` | optional client evidence (probe / `curl` / `ping -M do` from a VM) or Connection Monitor rows (KQL below) | `{"path","check","payload_bytes","result","via_nva","detail","source_resource_id"}`. `result`: `ok`/`pass`/`success` vs `fail`/`timeout`/`error`. Size: `check` containing `small`/`large`, else `payload_bytes` vs `thresholds.large_payload_bytes` |
| `thresholds` | optional | `large_payload_bytes` (default 1400) |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found". `next_hop_checks` and `flows`
are optional enrichments and do not create gaps when absent. `path_checks` without
`source_resource_id` are kept regardless of scope (client evidence has no ARM ID).

### What the control plane cannot see

Route tables, effective routes, NIC IP forwarding and BGP state are control-plane reads. They
cannot see **IP forwarding inside the appliance OS** (Learn: "You might need to enable IP
forwarding within the virtual machine's operating system"), the NVA's own firewall, or a path
MTU problem. So the engine:

- emits an evidence gap containing "guest OS forwarding" whenever a `VirtualAppliance` next hop
  is in a path and no `path_checks` were supplied;
- raises `RT-NVA-DATAPLANE` when probes through the NVA fail while no control-plane fault was
  found (SC-07 pattern);
- raises `RT-MTU-BLACKHOLE` when small checks pass and large ones fail on the same path, and
  records a gap when only small-payload checks exist — availability probes measure only small
  requests (MH-06 "the invisible fault").

## Steps

1. Inventory in scope: `az network route-table list -g <rg> -o json`,
   `az network nic list -g <rg> -o json`, `az network vnet list -g <rg> -o json`.
2. For each VNet (both sides of every peering):
   `az network vnet peering list -g <rg> --vnet-name <vnet> -o json`.
3. For each NIC on an affected source / return path:
   `az network nic show-effective-route-table -g <rg> -n <nic> -o json`.
4. Optional, per source VM and destination:
   `az network watcher show-next-hop -g <rg> --vm <vm> --source-ip <src-ip> --dest-ip <dst-ip> -o json`.
5. Optional data-plane evidence with `execute_kusto_query` (Connection Monitor; note these
   probes are small TCP/ICMP checks and stay green during an MTU black hole):

   ```kusto
   NWConnectionMonitorTestResult
   | where TimeGenerated > ago(1h)
   | project TimeGenerated, TestGroupName, SourceAddress, DestinationAddress, DestinationPort,
             Protocol, TestResult, ChecksFailed, ChecksTotal
   ```

   Map each row to `{"path": TestGroupName, "check": "small", "result": TestResult}`
   (`TestResult` states: `Pass`, `Fail`, `Warning`, `Indeterminate`). Add operator probe results
   for large payloads (for example `ping <dest> -c 10 -M do -s 1472` from a Linux VM, or a large
   HTTP download) as `check: "large"`.
6. Save inputs with `netscope.save_netops_input`, then run
   `python routing.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_routing_analyzer_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `RT-BLACKHOLE:<route-table>:<route>` | critical | UDR with next hop `None` — traffic is dropped (SC-03). Effective routes / next-hop checks that confirm it are merged into `evidence.observed_on` |
| `RT-BLACKHOLE-EFFECTIVE:<nic>:<prefix>` | critical | Active `User` effective route with next hop `None` not explained by a collected route table |
| `RT-NEXTHOP-NONE:<vm>:<dest-ip>` | critical (user route) / high (`System Route`) | Network Watcher next hop `None` |
| `RT-FLOW-BLACKHOLE:<flow>:<direction>` | critical (User) / high | Longest-prefix match for a flow direction is `None` |
| `RT-PEERING-NOT-CONNECTED:<vnet>:<peering>` | critical (Disconnected) / high (Initiated) | Peering not established on both sides |
| `RT-PEERING-ACCESS-DISABLED:<vnet>:<peering>` | critical | `allowVirtualNetworkAccess=false` — state can still be Connected; evidence shows whether the break is one-way (SC-06) |
| `RT-PEERING-FORWARDED-DISABLED:<vnet>:<peering>` | high | `allowForwardedTraffic=false` while the remote VNet hosts an NVA / firewall next hop or gateway transit is used (SC-06) |
| `RT-PEERING-NOT-SYNCED:<vnet>:<peering>` | medium | `peeringSyncLevel` is not `FullyInSync` |
| `RT-ASYMMETRIC:<flow>` | high | Forward path via an NVA / firewall but return path bypasses it, or different NVA IPs per direction |
| `RT-NVA-IPFWD-OFF:<nic>` | high | NIC owning a `VirtualAppliance` next hop IP has `enableIPForwarding=false` |
| `RT-NVA-DATAPLANE:<path>` | high | Data plane fails, control plane healthy — check guest OS IP forwarding / NVA firewall (SC-07) |
| `RT-MTU-BLACKHOLE:<path>` | high | Large payloads fail while small succeed: suspect MTU/MSS black-hole (MH-06 `mtu-blackhole`) |
| `RT-PATH-FAIL:<path>` | medium | Every check on a path fails; consistent with listed control-plane findings, or unexplained (hand off to `netops-nsg-firewall-audit`) |

Default system routes with next hop `None` (for example `10.0.0.0/8` when not in the VNet) are
normal and are not reported. A healthy VPN / BGP control plane with spoke-to-on-premises
traffic failing belongs here (UDR black hole, NVA forwarding); tunnel and BGP state belong to
`netops-hybrid-health`.

## KPI definition

`asymmetric_paths` — number of findings that black-hole or asymmetrically route traffic:
`RT-BLACKHOLE`, `RT-BLACKHOLE-EFFECTIVE`, `RT-NEXTHOP-NONE`, `RT-FLOW-BLACKHOLE`,
`RT-PEERING-NOT-CONNECTED`, `RT-PEERING-ACCESS-DISABLED`, `RT-ASYMMETRIC`, `RT-NVA-IPFWD-OFF`,
`RT-NVA-DATAPLANE`, `RT-MTU-BLACKHOLE`. Scorecard: good `<= 0`, critical `> 0`. Emitted only
when at least one routing input was collected.

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Examples (input → output):

- `examples/sc03-blackhole-input.json` → `examples/sc03-blackhole-output.json` (SC-03 bad spoke UDR)
- `examples/sc06-peering-input.json` → `examples/sc06-peering-output.json` (SC-06 peering misconfiguration)
- `examples/sc07-ipforward-input.json` → `examples/sc07-ipforward-output.json` (SC-07 NVA guest OS forwarding off)
- `examples/mh06-mtu-input.json` → `examples/mh06-mtu-output.json` (Microhack ch-06 `mtu-blackhole`)

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Network
Troubleshooter and VNet Architect specialists into `reference/` (see
[`reference/INDEX.md`](reference/INDEX.md)). Do not edit those files; they are rebuilt by
`node scripts/netops/build-netops.mjs`.

## Citations

- Virtual network traffic routing (next hop types, `None` drops traffic, longest prefix match, IP forwarding in the guest OS): https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview
- Route tables REST (`nextHopType`, `nextHopIpAddress`): https://learn.microsoft.com/rest/api/virtualnetwork/route-tables/get
- Effective route table REST (`addressPrefix[]`, `source`, `state`): https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get-effective-route-table
- Network Watcher next hop REST (`routeTableId` = `System Route`): https://learn.microsoft.com/rest/api/network-watcher/network-watchers/get-next-hop
- Manage VNet peering (Initiated / Connected, forwarded traffic): https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-peering
- VNet peering REST (`peeringState`, `peeringSyncLevel`, `allowVirtualNetworkAccess`, `allowForwardedTraffic`, `remoteAddressSpace`): https://learn.microsoft.com/rest/api/virtualnetwork/virtual-network-peerings/get
- Troubleshoot peering (Disconnected = one link deleted): https://learn.microsoft.com/troubleshoot/azure/virtual-network/virtual-network-troubleshoot-peering-issues
- Network interface REST (`enableIPForwarding`) and management: https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get, https://learn.microsoft.com/azure/virtual-network/virtual-network-network-interface
- Troubleshoot NVA (IP forwarding on the NIC): https://learn.microsoft.com/troubleshoot/azure/virtual-network/virtual-network-troubleshoot-nva
- Azure Firewall asymmetric routing: https://learn.microsoft.com/azure/firewall/integrate-lb
- TCP/IP performance tuning (MTU 1,500, PMTUD, MSS clamping 1,350 / tunnel MTU 1,400): https://learn.microsoft.com/azure/virtual-network/virtual-network-tcpip-performance-tuning
- Configure VM MTU (`ping -M do -s`, larger MTU not supported through gateways / global peering / internet): https://learn.microsoft.com/azure/virtual-network/how-to-virtual-machine-mtu
- Connection Monitor test states and table: https://learn.microsoft.com/azure/network-watcher/connection-monitor-overview, https://learn.microsoft.com/azure/azure-monitor/reference/tables/nwconnectionmonitortestresult
- Azure CLI: https://learn.microsoft.com/cli/azure/network/route-table, https://learn.microsoft.com/cli/azure/network/route-table/route, https://learn.microsoft.com/cli/azure/network/nic, https://learn.microsoft.com/cli/azure/network/vnet/peering, https://learn.microsoft.com/cli/azure/network/watcher

Analysis only — verify against vendor documentation before applying.
