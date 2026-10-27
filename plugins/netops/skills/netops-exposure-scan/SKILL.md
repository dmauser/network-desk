---
name: netops-exposure-scan
description: Read-only Internet exposure scan. Collects public IPs, NICs, NSGs, Application Gateways and PaaS resources (storage accounts, key vaults, SQL servers), then evaluates deterministically with exposure.py which ports are reachable from the Internet on public-IP NICs (subnet NSG + NIC NSG), management ports (22/3389/5985/5986) exposed, unattached and Basic SKU public IPs, public Application Gateways without WAF, and PaaS with public network access enabled. Use for "what is exposed to the internet", "RDP/SSH open", "public IP audit", "attack surface", "public network access".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): public IP
review, "Internet-facing / exposed", "open to the Internet", RDP / SSH exposed, WAF coverage,
public network access on PaaS, attack-surface review, and the scheduled exposure task (KPI
`risky_mgmt_exposures`).

Load `netops-managed-scope` first. Every collected resource must be inside the managed scope;
pass the resolved `managed_scopes` list into the engine, which drops (and counts) anything
outside it. Scheduled runs fail closed when the scope cannot be read.

**Read-only.** Every command below is a read or a documented read-equivalent diagnostic
(`readonly_guard.classify_az_command` returns `allow_read` / `allow_diagnostic`). The agent
never runs a write; findings carry human-run verification commands and commented change steps.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `public_ips` | `az network public-ip list -o json` | `ipAddress`, `ipConfiguration.id` (owner), `natGateway.id`, `sku.name` |
| `nics` | `az network nic list -o json` | `ipConfigurations[]`: `publicIPAddress.id`, `privateIPAddress`, `subnet.id`, `applicationSecurityGroups[]`; `networkSecurityGroup.id` |
| `nsgs` | `az network nsg list -o json` | `securityRules[]`, `defaultSecurityRules[]`, `subnets[]` (subnet association) |
| `app_gateways` | `az network application-gateway list -o json` | `sku.tier`, `firewallPolicy.id`, `webApplicationFirewallConfiguration` (`enabled`, `firewallMode`), `frontendIPConfigurations[].publicIPAddress` |
| `paas_resources` | `az storage account list -o json`, `az keyvault show -n <kv> -o json` (for each vault from `az keyvault list`), `az sql server list -o json` | Each item needs `type`. Supported: `Microsoft.Storage/storageAccounts` (`publicNetworkAccess`, `networkRuleSet`/`networkAcls`.`defaultAction`), `Microsoft.KeyVault/vaults` (`properties.publicNetworkAccess`, `properties.networkAcls.defaultAction`), `Microsoft.Sql/servers` (`publicNetworkAccess`). Other types are skipped with a warning |
| `bastions` | optional: `az network bastion list -o json` | Only used to suggest Bastion in management-port findings; no gap when absent |

An **absent** key means "not collected" and becomes an `evidence_gaps` entry (the result is
`partial`). An **empty list** means "collected, nothing found". A NIC whose NSG is missing from
`nsgs` gets its own evidence gap and is not evaluated.

## Steps

1. Inventory in scope: `az network public-ip list -o json`, `az network nic list -o json`,
   `az network nsg list -o json`.
2. Web front ends: `az network application-gateway list -o json`
   (WAF policies: `az network application-gateway waf-policy list -o json`).
3. PaaS: `az storage account list -o json`, `az keyvault list -o json` then
   `az keyvault show -n <kv> -o json` per vault (the list output omits network ACLs),
   `az sql server list -o json`; optional `az network bastion list -o json`.
4. Optional confirmation for a flagged NIC (attached VM must be running):
   `az network nic list-effective-nsg -g <rg> -n <nic> -o json`.
5. Save inputs with `netscope.save_netops_input`, then run
   `python exposure.py input.json > result.json` (ExecutePythonCode) and render with
   `netops-report-renderer` (`models.build_exposure_scan_model`).

## Evaluation model

For every NIC IP configuration with a public IP, the engine evaluates Internet-sourced inbound
TCP and UDP in priority order (first match wins) through the subnet NSG and then the NIC NSG;
traffic is exposed only when **both** allow it. A rule matches when its source is `*`,
`Internet`, `0.0.0.0/0` or `::/0` and its destination is `*`, `VirtualNetwork`, a prefix
containing the NIC private IP, or an ASG the IP configuration belongs to. Default rules are
used when collected; otherwise the platform `DenyAllInBound` applies. With no NSG at all a
Standard SKU public IP is closed (secure by default) and a Basic SKU public IP is open.
Public IPs on load balancers, gateways and other services are counted but not port-evaluated.

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `EXP-MGMT-EXPOSED:<nic>:<port>` | critical | TCP 22 / 3389 / 5985 / 5986 reachable from the Internet (one per port, counts into `risky_mgmt_exposures`) |
| `EXP-APPGW-NO-WAF:<agw>` | high | Public Application Gateway not on a WAF tier or without WAF policy / enabled WAF config |
| `EXP-PAAS-OPEN:<name>` | high (`defaultAction` Allow) / medium (not reported) | Storage account / key vault with public network access enabled and no default deny |
| `EXP-PORT-EXPOSED:<nic>` | medium | Other TCP/UDP ports reachable from the Internet on a public-IP NIC |
| `EXP-APPGW-WAF-DETECTION:<agw>` | medium | WAF config in Detection mode (logs only) |
| `EXP-PIP-UNATTACHED:<pip>` | low | Public IP with no IP configuration and no NAT gateway |
| `EXP-PIP-BASIC:<pip>` | low | Basic SKU public IP (retired September 30, 2025; open by default) |
| `EXP-PAAS-FIREWALLED:<name>` | low (with IP/VNet rules) / info | Public endpoint enabled but default action Deny |
| `EXP-SQL-PUBLIC:<name>` | low | SQL server public network access Enabled; review server firewall rules |

KPI: `risky_mgmt_exposures` = number of `EXP-MGMT-EXPOSED` findings, emitted only when
`nics` and `nsgs` were both collected (scorecard: good = 0).

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`; each finding
`{id, skill, severity, resource_id, title, evidence, recommendation, remediation_script, citations[]}`.
Example: `examples/internet-exposure-input.json` → `examples/internet-exposure-output.json`.

## Network Desk reference

Design-time knowledge for this domain is generated from the Network Desk Network Security
specialist into `reference/` (see `reference/INDEX.md`). Do not edit those files; they are
rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- How NSGs filter traffic (subnet then NIC for inbound): https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works
- NSG overview and default rules: https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
- Public IP SKUs (Standard secure by default, Basic open by default): https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-addresses
- Basic SKU public IP retirement: https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-basic-upgrade-guidance
- Public IP and NIC REST schemas: https://learn.microsoft.com/rest/api/virtualnetwork/public-ip-addresses/get and https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get
- Management ports protected by just-in-time access: https://learn.microsoft.com/azure/defender-for-cloud/just-in-time-access-usage
- Disable direct RDP / SSH from the Internet: https://learn.microsoft.com/azure/security/fundamentals/network-best-practices
- Application Gateway schema (`sku.tier`, `firewallPolicy`, `webApplicationFirewallConfiguration`): https://learn.microsoft.com/rest/api/application-gateway/application-gateways/get
- Storage account network rules: https://learn.microsoft.com/rest/api/storagerp/storage-accounts/get-properties
- Key Vault network ACLs: https://learn.microsoft.com/rest/api/keyvault/keyvault/vaults/get
- SQL server public network access: https://learn.microsoft.com/rest/api/sql/servers/get
- Azure CLI: https://learn.microsoft.com/cli/azure/network/public-ip, https://learn.microsoft.com/cli/azure/network/nic, https://learn.microsoft.com/cli/azure/network/application-gateway, https://learn.microsoft.com/cli/azure/storage/account, https://learn.microsoft.com/cli/azure/keyvault, https://learn.microsoft.com/cli/azure/sql/server, https://learn.microsoft.com/cli/azure/network/bastion

Analysis only — verify against vendor documentation before applying.
