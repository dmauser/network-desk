---
name: netops-flow-insights
description: Read-only flow-log coverage and Traffic Analytics insights for Azure virtual networks. Collects VNets, Network Watcher flow logs and NTANetAnalytics / NTAIpDetails query results, then scores them deterministically with flows.py (VNets without virtual network flow logs, disabled flow logs, Traffic Analytics not enabled, NSG flow logs still in use before the 30 September 2027 retirement, high denied-flow volume to a destination/port, MaliciousFlow traffic, top talkers). Use for "flow logs missing", "telemetry gap", "Traffic Analytics", "denied flows", "top talkers".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): flow logs
missing or disabled, telemetry / logging gaps, Traffic Analytics questions, denied flows,
top talkers, suspicious (malicious) flows, weekly flow-log coverage task.

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Flow logs are scoped by their `targetResourceId` (the flow log resource itself
lives under the Network Watcher resource group). Scheduled runs fail closed when the scope
cannot be read.

**Read-only.** Every command below is a read (`readonly_guard.classify_az_command` returns
`allow_read`) or a Log Analytics query. The agent never runs a write; findings carry
human-run verification commands and commented change steps only.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `vnets` | `az network vnet list -o json` | Denominator of the coverage KPI |
| `flow_logs` | `az network watcher flow-log list --location <region> -o json` for every region in scope | `targetResourceId` (VNet, subnet, NIC or NSG), `enabled`, `retentionPolicy`, `flowAnalyticsConfiguration.networkWatcherFlowAnalyticsConfiguration` (`enabled`, `workspaceResourceId`, `trafficAnalyticsInterval`). Flattened CLI objects and ARM `properties` objects are both accepted |
| `flow_rows` | KQL 1 (`Query` = `flow_summary`) and KQL 4 (`Query` = `malicious`) below via `execute_kusto_query` | NTANetAnalytics columns only; rows whose `TargetResourceId` is an ARM id are scope-filtered |
| `ip_details` | KQL 6 below (optional) | NTAIpDetails `Ip`, `FlowType`, `ThreatType`, `ThreatDescription`, `Location` enrich `FLOW-MALICIOUS` |
| `thresholds` | optional | `denied_flows` (default 100 per destination/port/protocol), `top_talkers` (default 3) |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`); a missing `flow_rows` is reported as "Traffic Analytics data not queried". An
**empty list** means "collected, nothing found".

## Steps

1. Inventory in scope: `az network vnet list -o json`; note each VNet `location`.
2. Flow logs per region: `az network watcher flow-log list --location <region> -o json`
   (detail: `az network watcher flow-log show --location <region> --name <flow-log> -o json`).
3. If any enabled flow log has Traffic Analytics, query its `workspaceResourceId` workspace with
   `execute_kusto_query` (window: incident window, or last 24 h for scheduled runs). Use only
   `SubType == "FlowLog"` rows (`StatusMessage` rows are service status).

   KQL 1 — flow summary (engine input, `Query` = `flow_summary`):

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(24h)
   | where SubType == "FlowLog"
   | summarize AllowedInFlows = sum(AllowedInFlows), AllowedOutFlows = sum(AllowedOutFlows),
               DeniedInFlows = sum(DeniedInFlows), DeniedOutFlows = sum(DeniedOutFlows),
               BytesSrcToDest = sum(BytesSrcToDest), BytesDestToSrc = sum(BytesDestToSrc)
       by TargetResourceId, FlowType, SrcIp, DestIp, DestPort, L4Protocol, AclGroup, AclRule
   | extend Query = "flow_summary"
   ```

   KQL 2 — top denied flows (`FlowStatus` `D` = denied):

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(24h)
   | where SubType == "FlowLog" and FlowStatus == "D"
   | summarize Denied = sum(DeniedInFlows + DeniedOutFlows) by DestIp, DestPort, L4Protocol, AclGroup, AclRule
   | top 20 by Denied desc
   ```

   KQL 3 — top talkers:

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(24h)
   | where SubType == "FlowLog" and isnotempty(SrcIp) and isnotempty(DestIp)
   | summarize Bytes = sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp
   | top 10 by Bytes desc
   ```

   KQL 4 — malicious / external flows (engine input, `Query` = `malicious`). For `AzurePublic`,
   `ExternalPublic` and `MaliciousFlow` rows `SrcIp`/`DestIp` are blank and the public IPs are in
   `SrcPublicIps` / `DestPublicIps` (space-separated `ip|...` entries); counters are per row, so
   they are repeated for each expanded IP:

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(24h)
   | where SubType == "FlowLog" and FlowType == "MaliciousFlow"
   | extend PublicIps = iff(isnotempty(SrcPublicIps), SrcPublicIps, DestPublicIps)
   | mv-expand Entry = split(PublicIps, " ") to typeof(string)
   | extend PublicIp = tostring(split(Entry, "|")[0])
   | summarize AllowedInFlows = sum(AllowedInFlows), AllowedOutFlows = sum(AllowedOutFlows),
               DeniedInFlows = sum(DeniedInFlows), DeniedOutFlows = sum(DeniedOutFlows)
       by TargetResourceId, FlowType, PublicIp, FlowDirection, DestPort
   | extend Query = "malicious"
   ```

   Change `FlowType == "MaliciousFlow"` to `FlowType in ("ExternalPublic", "AzurePublic")` to
   review Internet / Azure public traffic (not scored by the engine).

   KQL 5 — flows by NSG rule:

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(24h)
   | where SubType == "FlowLog"
   | summarize Allowed = sum(AllowedInFlows + AllowedOutFlows), Denied = sum(DeniedInFlows + DeniedOutFlows)
       by AclGroup, AclRule, FlowStatus
   | order by Denied desc
   ```

   KQL 6 — threat details for malicious IPs (`ip_details`):

   ```kusto
   NTAIpDetails
   | where TimeGenerated > ago(24h)
   | where FlowType == "MaliciousFlow"
   | summarize arg_max(TimeGenerated, *) by Ip
   | project Ip, FlowType, ThreatType, ThreatDescription, Location
   ```

4. Save inputs with `netscope.save_netops_input`, then run
   `python flows.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_flow_insights_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `FLOW-VNET-NO-FLOWLOG:<vnet>` | medium | No enabled flow log whose `targetResourceId` is the VNet (subnet-only logs are listed in evidence); lowers the coverage KPI |
| `FLOW-LOG-DISABLED:<flow-log>` | medium (VNet/subnet/NIC), low (NSG) | Flow log exists with `enabled: false` |
| `FLOW-TA-DISABLED:<flow-log>` | low | Enabled flow log without Traffic Analytics (records only in storage) |
| `FLOW-NSG-FLOWLOG-RETIRING:<flow-log>` | medium (enabled), low (disabled) | NSG flow logs retire on 30 September 2027; new ones can't be created; migrate to virtual network flow logs |
| `FLOW-DENIED-HIGH:<dest-ip>:<port>/<proto>` | medium | Denied flows to one destination/port >= `denied_flows`: investigate blocked traffic (possible SC-04 style deny); hand off rule review to `netops-nsg-firewall-audit` |
| `FLOW-MALICIOUS:<public-ip>` | high | Traffic Analytics `FlowType == "MaliciousFlow"`; allowed counts mean the path is open |

Top talkers (bytes in both directions per `SrcIp` → `DestIp`) are reported as metrics only.
`FlowType` values: `IntraVNet`, `InterVNet`, `S2S`, `P2S`, `AzurePublic`, `ExternalPublic`,
`MaliciousFlow`, `Unknown Private`, `Unknown`. `L4Protocol`: `T` (TCP) / `U` (UDP).

KPI: `flow_log_coverage_pct` = in-scope VNets with an enabled virtual network flow log ÷ in-scope
VNets × 100 (scorecard: good >= 100, warning >= 80). Emitted only when both `vnets` and
`flow_logs` were collected.

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Example: `examples/flowlog-coverage-input.json` → `examples/flowlog-coverage-output.json`.

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Network Monitor and Network
Security specialists into `reference/` (see [reference/INDEX.md](reference/INDEX.md)). Do not
edit those files; they are rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- Virtual network flow logs: https://learn.microsoft.com/azure/network-watcher/vnet-flow-logs-overview
- NSG flow logs (retirement 30 September 2027, migration): https://learn.microsoft.com/azure/network-watcher/nsg-flow-logs-overview
- Azure CLI `az network watcher flow-log`: https://learn.microsoft.com/cli/azure/network/watcher/flow-log
- Flow Logs - Get (targetResourceId, enabled, retentionPolicy, flowAnalyticsConfiguration): https://learn.microsoft.com/rest/api/network-watcher/flow-logs/get
- NTANetAnalytics table reference: https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntanetanalytics
- NTAIpDetails table reference: https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntaipdetails
- Traffic Analytics schema (FlowStatus, FlowType, public IP fields, SubType): https://learn.microsoft.com/azure/network-watcher/traffic-analytics-schema

Analysis only — verify against vendor documentation before applying.
