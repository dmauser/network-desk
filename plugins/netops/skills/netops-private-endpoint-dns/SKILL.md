---
name: netops-private-endpoint-dns
description: Read-only private endpoint and private DNS validation. Collects private endpoints, DNS zone groups, private DNS zones, virtual network links and A records (plus optional resolution checks from a client), then validates deterministically with pedns.py — connection approval, zone group present, recommended privatelink zone for the subresource, zone linked to the resolver VNets, A record present and matching the endpoint IP, NxDomainRedirect fallback, public resolution. Use for "PaaS unreachable via private endpoint", "resolves to public IP", "NXDOMAIN", "private DNS".
---

## When to use

Symptoms routed here by `netops-investigator` (see `../../agents/routing.json`): private
endpoint / Private Link not working, PaaS service unreachable, FQDN resolves to a public IP
or NXDOMAIN, private DNS zone / zone group / virtual network link questions, weekly PE-DNS
validation task.

Load `netops-managed-scope` first and pass `managed_scopes` to the engine. Resources outside
the managed scope are dropped and counted in `warnings`; scheduled runs fail closed.

**Read-only.** Every command below is a read (`readonly_guard.classify_az_command` →
`allow_read`). Fix-it commands appear only as commented, human-run lines in
`remediation_script`.

## Inputs

| Key | Source (read-only) | Notes |
| --- | --- | --- |
| `private_endpoints` | `az network private-endpoint list -g <rg> -o json` | `privateLinkServiceConnections[]` / `manualPrivateLinkServiceConnections[]` → `privateLinkServiceConnectionState.status` (`Pending`, `Approved`, `Rejected`, `Disconnected`); `customDnsConfigs[]`; `subnet.id` |
| `dns_zone_groups` | `az network private-endpoint dns-zone-group list -g <rg> --endpoint-name <pe> -o json` wrapped as `{"private_endpoint_id", "value"}` | `privateDnsZoneConfigs[].privateDnsZoneId`, `recordSets[]` (`recordSetName`, `ipAddresses`), `provisioningState` |
| `private_dns_zones` | `az network private-dns zone list -o json` | |
| `vnet_links` | `az network private-dns link vnet list -g <zone-rg> -z <zone> -o json` | `virtualNetwork.id`, `virtualNetworkLinkState` (`Completed`; some SDKs report `Done`), `registrationEnabled`, `resolutionPolicy` (`Default` / `NxDomainRedirect`) |
| `a_records` | `az network private-dns record-set a list -g <zone-rg> -z <zone> -o json` | `name`, `aRecords[].ipv4Address` |
| `resolver_vnets` | operator / topology | VNets whose DNS uses Azure-provided DNS (168.63.129.16), for example the hub with DNS Private Resolver plus spokes using Azure DNS. Default: each PE's own VNet |
| `resolution_checks` | optional client evidence (`nslookup` output from a VM, or a Connection Monitor / probe log) | `{"fqdn", "resolved_ips", "from"}` |

Absent key → `evidence_gaps` entry and `partial: true`; empty list → collected, none found.

## Steps

1. `az network private-endpoint list -g <rg> -o json` for every in-scope resource group.
2. For each PE: `az network private-endpoint dns-zone-group list -g <rg> --endpoint-name <pe> -o json`.
3. `az network private-dns zone list -o json`; for each `privatelink.*` zone in scope:
   `az network private-dns link vnet list -g <zone-rg> -z <zone> -o json` and
   `az network private-dns record-set a list -g <zone-rg> -z <zone> -o json`.
4. Optional client evidence (the agent cannot run `nslookup` inside a VM; ask the user or read a
   probe log in Log Analytics).
5. Save inputs with `netscope.save_netops_input`, run `python pedns.py input.json`, and render
   with `netops-report-renderer` (`models.build_private_endpoint_dns_model`).

### Recommended zones checked by the engine

| Subresource (`groupIds`) | Private DNS zone |
| --- | --- |
| `blob` | `privatelink.blob.core.windows.net` |
| `file` | `privatelink.file.core.windows.net` |
| `queue` | `privatelink.queue.core.windows.net` |
| `table` | `privatelink.table.core.windows.net` |
| `dfs` | `privatelink.dfs.core.windows.net` |
| `web` | `privatelink.web.core.windows.net` |
| `sqlServer` | `privatelink.database.windows.net` |
| `vault` | `privatelink.vaultcore.azure.net` |
| `registry` | `privatelink.azurecr.io` |
| `sites` | `privatelink.azurewebsites.net` |
| `Sql` (Cosmos DB) | `privatelink.documents.azure.com` |
| `namespace` (Event Hubs / Service Bus) | `privatelink.servicebus.windows.net` |
| `account` (Azure AI services) | `privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com` |
| `searchService` | `privatelink.search.windows.net` |

Other subresources skip the zone-name check (zone links and records are still validated).

## Interpretation

| Finding id | Severity | Meaning |
| --- | --- | --- |
| `PE-CONN-PENDING:<pe>` | high | Connection awaits approval by the target owner |
| `PE-CONN-REJECTED:<pe>` / `PE-CONN-DISCONNECTED:<pe>` | critical | Connection carries no traffic |
| `PE-NO-ZONE-GROUP:<pe>` | high (no matching zone) / medium | Records not managed automatically |
| `PE-ZONE-GROUP-FAILED:<pe>` | high | Zone group `provisioningState` is `Failed` |
| `PE-WRONG-ZONE:<pe>` | high | Registered in a zone other than the recommended one |
| `PE-ZONE-MISSING:<pe>:<zone>` | high | Referenced zone not found in scope |
| `PE-ZONE-NOT-LINKED:<zone>:<vnet>` | high | Resolver VNet has no link to the zone |
| `PE-LINK-NOT-READY:<zone>:<link>` | medium | Link not `Completed` |
| `PE-LINK-NXDOMAIN-REDIRECT:<zone>:<link>` | info | Fallback to internet enabled; may mask a missing record |
| `PE-DNS-RECORD-MISSING:<zone>:<record>` | critical | A record deleted / never registered (SC-05) |
| `PE-DNS-RECORD-MISMATCH:<zone>:<record>` | critical | A record IP differs from the PE NIC IP |
| `PE-RESOLVE-NXDOMAIN` / `PE-RESOLVES-PUBLIC` / `PE-RESOLVES-UNKNOWN-IP` | critical / critical / high | Client evidence contradicts the expected private IP |
| `PE-DNS-STALE-RECORD:<zone>:<record>` | info | Record in a privatelink zone pointing to no in-scope PE |

Planned changes in non-`privatelink` zones (for example a new on-premises/corporate A record,
SC-08) produce **no** findings by design: a change that is working as intended must not raise
an alert.

KPI: `pe_dns_healthy_pct` = private endpoints with no critical/high/medium issue ÷ all in-scope
private endpoints.

## Output schema

NetOps result envelope (`netops-report-renderer/models.py`):
`{skill, findings[], evidence_gaps[], metrics[], kpis{}, partial, warnings[]}`.
Example: `examples/sc05-record-removed-input.json` → `examples/sc05-record-removed-output.json`.

## Network Desk reference

Design-time knowledge is generated from the Network Desk Private Link and DNS specialists into
`reference/` (see `reference/INDEX.md`); rebuilt by `node scripts/netops/build-netops.mjs`.

## Citations

- Private endpoint DNS zone values: https://learn.microsoft.com/azure/private-link/private-endpoint-dns
- Private endpoint DNS integration scenarios: https://learn.microsoft.com/azure/private-link/private-endpoint-dns-integration
- Connection approval states: https://learn.microsoft.com/troubleshoot/azure/private-link/troubleshoot-private-endpoint-pending-approval and https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Private DNS zone group API: https://learn.microsoft.com/rest/api/virtualnetwork/private-dns-zone-groups/get
- Virtual network links: https://learn.microsoft.com/azure/dns/private-dns-virtual-network-links
- Fallback to internet (`NxDomainRedirect`): https://learn.microsoft.com/azure/dns/private-dns-fallback and https://learn.microsoft.com/troubleshoot/azure/dns/troubleshoot-private-dns-zone-override-nxdomain
- Azure CLI: https://learn.microsoft.com/cli/azure/network/private-endpoint, https://learn.microsoft.com/cli/azure/network/private-endpoint/dns-zone-group, https://learn.microsoft.com/cli/azure/network/private-dns/link/vnet, https://learn.microsoft.com/cli/azure/network/private-dns/record-set/a

Analysis only — verify against vendor documentation before applying.
