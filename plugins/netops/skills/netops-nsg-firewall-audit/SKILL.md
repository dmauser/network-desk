---
name: netops-nsg-firewall-audit
description: Read-only audit of network security group rules and Azure Firewall policy rule collection groups. Collects NSGs (custom + default rules, subnet/NIC associations), optional firewall policy rule collection groups and optional Traffic Analytics per-rule hit counts, then scores them deterministically with ruleaudit.py (overly broad Internet allows, management ports from the Internet, deny-all rules shadowing allows, shadowed/redundant rules, IKE/IPsec UDP 500/4500 blocked, unassociated NSGs, unused rules with evidence, wildcard Azure Firewall allows). Use for "traffic blocked by NSG", "new deny rule", "shadowed rule", "overly permissive rules", "NSG audit".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): traffic
"blocked by the NSG / firewall", "denied by" a security rule, a new deny rule overriding
existing rules, shadowed or overly broad (any-any) rules, Azure Firewall policy review, and
the scheduled rule-hygiene task (KPI `broad_rules`).

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read (`readonly_guard.classify_az_command` returns
`allow_read`). The agent never runs a write; findings carry human-run verification commands
and commented change steps only.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `nsgs` | `az network nsg list -o json` (or per NSG `az network nsg rule list -g <rg> --nsg-name <nsg> --include-default`) | `securityRules[]`, `defaultSecurityRules[]`: `priority`, `direction`, `access`, `protocol`, `sourceAddressPrefix(es)`, `destinationAddressPrefix(es)`, `sourcePortRange(s)`, `destinationPortRange(s)`, `source/destinationApplicationSecurityGroups[]`; `subnets[]`, `networkInterfaces[]` |
| `firewall_rule_collection_groups` | `az network firewall policy rule-collection-group list -g <rg> --policy-name <policy> -o json` | `ruleCollections[]` (`ruleCollectionType`, `action.type`, `rules[]` with `ruleType`, `sourceAddresses`, `destinationAddresses`, `destinationPorts`, `targetFqdns`) |
| `rule_hits` | KQL below (Traffic Analytics `NTANetAnalytics`) reduced to `[{"nsg_id", "rule", "hits"}]` | `nsg_id` = NSG ARM id or name, `rule` = rule name |
| `rule_hits_window` | optional string, for example `"30d"` | Shown in unused-rule evidence |
| `thresholds` | optional | `broad_port_count` (default 1024): ports from Internet that make an allow "overly broad" |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found".

**Unused rules need evidence.** The engine reports a rule as unused only when `rule_hits`
contains an explicit `hits: 0` entry for it. Fill zero entries only for custom rules of NSGs
whose flow logs / Traffic Analytics covered the whole window; without `rule_hits` the result
carries an evidence gap and no rule is called unused.

**Azure Firewall.** `az network firewall policy rule-collection-group` belongs to the
`azure-firewall` CLI extension. If the extension is not available to the agent, leave
`firewall_rule_collection_groups` absent: the engine records an evidence gap instead of
guessing.

## Steps

1. Inventory in scope: `az network nsg list -o json` (includes `defaultSecurityRules`,
   `subnets`, `networkInterfaces`). For one NSG:
   `az network nsg rule list -g <rg> --nsg-name <nsg> --include-default -o json`.
2. Azure Firewall (optional): `az network firewall policy list -o json`, then for each policy
   `az network firewall policy rule-collection-group list -g <rg> --policy-name <policy> -o json`.
3. Rule hits (optional, needs VNet/NSG flow logs with Traffic Analytics) with `execute_kusto_query`:

   ```kusto
   NTANetAnalytics
   | where TimeGenerated > ago(30d)
   | where SubType == "FlowLog"
   | summarize hits = sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows) by AclGroup, AclRule
   ```

   Map `AclGroup` to `nsg_id` and `AclRule` to `rule`; add `hits: 0` for custom rules absent
   from the result only when flow logging covered the full window.
4. Save inputs with `netscope.save_netops_input`, then run
   `python ruleaudit.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_nsg_firewall_audit_model`).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `NSG-DENY-ALL-SHADOWS:<nsg>:<rule>` | critical (inbound) / high (outbound) | A deny with protocol, source, destination and ports `*` sits above allow rules: "deny-all shadows N allow rules" (SC-04) |
| `NSG-MGMT-FROM-INTERNET:<nsg>:<rule>` | critical | Inbound allow from `*` / `Internet` / `0.0.0.0/0` covering TCP 22, 3389, 5985 or 5986 |
| `NSG-BROAD-ALLOW:<nsg>:<rule>` | high | Inbound allow from `*` / `Internet` / `0.0.0.0/0` with `broad_port_count`+ destination ports (counts into `broad_rules`) |
| `NSG-IKE-BLOCKED:<nsg>:<rule>` | high | A deny explicitly covering UDP 500 / 4500: "blocks IKE/IPsec (UDP 500/4500)" (SC-02) |
| `AFW-BROAD-ALLOW:<policy>:<rcg>:<collection>:<rule>` | high | Filter collection allow with source `*` and destination `*` or ports `*` (network rule) or FQDN `*` (application rule) (counts into `broad_rules`) |
| `NSG-SHADOWED:<nsg>:<rule>` | medium | Rule fully covered by a higher-priority rule of the opposite access in the same direction; it never matches |
| `NSG-REDUNDANT:<nsg>:<rule>` | low | Rule fully covered by a higher-priority rule with the same access |
| `NSG-UNASSOCIATED:<nsg>` | low | NSG attached to no subnet and no NIC |
| `NSG-UNUSED-RULE:<nsg>:<rule>` | low | Explicit `hits: 0` over `rule_hits_window` |

Shadowing uses conservative containment: `*` covers everything, CIDRs are compared with
prefix containment, service tags and ASGs must match exactly, and anything unparsable is
treated as **not** covered (no false shadowing). Only custom rules are checked; default rules
(priority 65000+) are never reported. Rules that are already shadowed are not reported again
as broad or management exposures.

A rule on the NSG is not proof the packet reached it: for inbound traffic Azure evaluates the
subnet NSG first, then the NIC NSG. To confirm what a VM actually gets, hand off to
`netops-exposure-scan` (Internet exposure) or use IP flow verify.

KPI: `broad_rules` = `NSG-BROAD-ALLOW` + `AFW-BROAD-ALLOW` count (scorecard: good <= 0,
warning <= 5).

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Examples: `examples/sc04-deny-all-input.json` → `examples/sc04-deny-all-output.json`,
`examples/sc02-ike-block-input.json` → `examples/sc02-ike-block-output.json`.

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Network Security and
Firewall specialists into `reference/` (see `reference/INDEX.md`). Do not edit those files;
they are rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- NSG overview (priority 100-4096, default rules): https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
- How NSGs filter traffic (subnet then NIC for inbound): https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works
- NSG REST schema (`securityRules`, `defaultSecurityRules`, protocol / access / direction enums): https://learn.microsoft.com/rest/api/virtualnetwork/network-security-groups/get
- Service tags (`Internet`, `VirtualNetwork`): https://learn.microsoft.com/azure/virtual-network/service-tags-overview
- Management ports protected by just-in-time access (22, 3389, 5985, 5986): https://learn.microsoft.com/azure/defender-for-cloud/just-in-time-access-usage
- Disable direct RDP / SSH from the Internet: https://learn.microsoft.com/azure/security/fundamentals/network-best-practices
- IKE / NAT-T ports (UDP 500 / 4500): https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-vpn-faq
- Traffic Analytics schema and `NTANetAnalytics` table: https://learn.microsoft.com/azure/network-watcher/traffic-analytics-schema and https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntanetanalytics
- Firewall policy rule collection groups (REST and CLI): https://learn.microsoft.com/rest/api/firewall/firewall-policy-rule-collection-groups/get and https://learn.microsoft.com/cli/azure/network/firewall/policy/rule-collection-group
- Azure CLI: https://learn.microsoft.com/cli/azure/network/nsg, https://learn.microsoft.com/cli/azure/network/nsg/rule, https://learn.microsoft.com/cli/azure/network/firewall/policy

Analysis only — verify against vendor documentation before applying.
