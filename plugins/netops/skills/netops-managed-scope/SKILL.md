---
name: netops-managed-scope
description: Read-only scope and safety guard for every NetOps skill. Dynamically reads the Azure SRE Agent managedResources configuration, canonicalizes subscription/resource-group/management-group scopes, filters network resource inventories to the managed scope with exact coverage, applies fail-closed scheduled or explicitly confirmed interactive policy (scope.py, copied verbatim from FinOps), and classifies every Azure CLI command as read, documented read-equivalent diagnostic, or denied (readonly_guard.py).
---

## Purpose

Load this skill **before** any NetOps skill reads Azure networking state. It keeps a
scheduled task from silently reading beyond the agent's managed resources, makes broader
interactive requests visible to the user, and enforces the NetOps read-only contract.
Broad Azure RBAC is not evidence that a scope is managed: `managedResources` remains the
policy boundary even when the agent identity can read more.

The bundled Python is pure offline logic and makes **no Azure calls**. Keep the whole
directory together: `scope.py` loads its `_scope_resolution.py` sibling and `netscope.py`
loads `scope.py` relative to `__file__`, so direct imports do not depend on `sys.path`.

| File | Role |
| --- | --- |
| `scope.py`, `_scope_resolution.py` | Copied from `dmauser/finops-sre-agent-pack@ac81cd15` (renamed only). Identical scope-policy semantics. |
| `netscope.py` | `filter_resources`, `scope_summary`, `save_netops_input` / `load_netops_input`. |
| `readonly_guard.py` | `classify_az_command`, `assert_read_only`, `classify_arm_action`, `DIAGNOSTIC_ACTIONS`. |

## 1. Read the live managed scope every run

Do not cache, copy from the manifest, or infer scope from prior conversations. Read the
current agent resource dynamically:

```bash
az resource show --ids <AGENT_RESOURCE_ID> \
  --query properties.knowledgeGraphConfiguration.managedResources -o json
```

Entries may be scope strings or objects with `id`, `resourceId`, or `scope`. Only
subscription, resource-group, and management-group scope IDs are accepted. If
`AGENT_RESOURCE_ID` is unavailable, the read fails, the result is malformed or empty, or
required expansion cannot be completed, a scheduled run must stop **fail closed**.

## 2. Discover management-group descendants when needed

Management-group membership is not encoded in a resource ID. For each configured
management group, collect **all** descendant subscriptions (not only direct children):

```bash
az account management-group show --name <MANAGEMENT_GROUP_ID> --expand --recurse -o json
```

or use Azure Resource Graph subscription containers and
`properties.managementGroupAncestorsChain`. Pass the result as
`management_group_expansions`; `scope.py` handles recursion, overlap, casing and cycles.

## 3. Resolve and enforce

```python
from netscope import decide_scope_policy, filter_resources, scope_summary

decision = decide_scope_policy(
    requested_scopes,            # scopes or resource IDs the user/task asked about
    managed_resources,
    mode="scheduled",            # or "interactive"
    management_group_expansions=mg_descendants,
)
```

- **Scheduled:** strict and fail closed. Never continue for an outside scope, malformed or
  empty managed scope, or an unexpanded management group. No override exists.
- **Interactive:** continue directly only when everything requested is contained. A
  broader request returns `outside_scope_confirmation_required`; show the exact
  `outside_scopes` and the `confirmation_key`, and re-evaluate in a later turn with
  `outside_scope_confirmed=True` and `confirmation_key=<DISPLAYED_KEY>`. Missing or
  mismatched keys stay confirmation-required. Silence, ambiguity, or a decline is denial.
  Confirmation never changes managedResources and never becomes a standing permission.

## 4. Filter every inventory before analysis

Query each effective scope independently (Resource Graph `az graph query` with
`--subscriptions`, or `az network ... list -g <rg>`), merge, then filter defensively:

```python
coverage = filter_resources(resources, managed_resources,
                            management_group_expansions=mg_descendants)
```

`filter_resources` accepts ARM objects (`id`), Resource Graph rows, Log Analytics rows
(`_ResourceId` / `ResourceId`) or bare IDs, de-duplicates case-insensitively, and returns
`included`, `excluded`, `unattributed`, their counts, `duplicate_count` and
`coverage_pct`. Analyse **only** `included`. Report excluded and unattributed counts in
every report; never hide them and never attribute an unattributed row by guesswork. Put
`scope_summary(managed_resources)` in the report header.

## 5. Read-only contract (enforced by `readonly_guard.py`)

Before running **any** Azure CLI command, call `assert_read_only(command)`. The guard
fails closed: unknown verbs, shell operators (`;`, `&&`, `||`, `|`, `>`, backticks,
`$(`), `az account set`, every create/update/delete/set/start/stop/wait verb,
secret-revealing commands (`shared-key`, `list-keys`, `show-device-config-script`, ...),
and `az rest` with any method other than GET (outside the diagnostic allowlist) are
denied. Remediation is **never** executed: skills emit a script for a human to review.

Allowed read-equivalent diagnostics (ARM models them as POST; they return state only).
Reader (`*/read`) does not grant the `/action` entries, so the optional custom role
**NetOps Network Diagnostics Reader** contains exactly these actions:

| Azure CLI | Required action |
| --- | --- |
| `az network nic show-effective-route-table` | `Microsoft.Network/networkInterfaces/effectiveRouteTable/action` |
| `az network nic list-effective-nsg` | `Microsoft.Network/networkInterfaces/effectiveNetworkSecurityGroups/action` |
| `az network vnet-gateway list-bgp-peer-status` | `Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action` |
| `az network vnet-gateway list-learned-routes` | `Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action` |
| `az network vnet-gateway list-advertised-routes` | `Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action` |
| `az network watcher show-next-hop` | `Microsoft.Network/networkWatchers/nextHop/action` |
| `az network watcher test-ip-flow` | `Microsoft.Network/networkWatchers/ipFlowVerify/action` |
| `az network watcher show-security-group-view` | `Microsoft.Network/networkWatchers/securityGroupView/action` |
| `az network watcher show-topology` | `Microsoft.Network/networkWatchers/topology/action` |
| `az network express-route list-route-tables` / `list-route-tables-summary` / `list-arp-tables` | `.../expressRouteCircuits/peerings/routeTables/read`, `routeTablesSummary/read`, `arpTables/read` (covered by Reader) |

Explicitly **excluded**: `az network watcher test-connectivity` (connectivityCheck may
install the Network Watcher VM extension), connection troubleshoot, packet capture, and
connection monitor creation.

If the SRE Agent's `RunAzCliReadCommands` tool rejects a POST-backed diagnostic, do not
work around it. Record the gap (`evidence_gaps`) and continue with GET-only evidence
(for example the route table and NSG resources attached to the subnet/NIC).

## 6. Pass every input through a deterministic file

Right after each Azure call (or once after a batch), save the response under a fixed name
and load it by name in the analysis step:

```python
from netscope import save_netops_input, load_netops_input

save_netops_input("gateways", source_path="tmp/ToolOutputs/<file reported for the call>.json")
save_netops_input("bgp-peers", bgp_json)          # inline response
peers = load_netops_input("bgp-peers", default=None)  # None => source unavailable (gap)
```

Files go to `tmp/netops-data/<name>.json`. Delete `tmp/netops-data/` at the start of a
scheduled run so stale inputs never leak in. A missing file is a reported gap, never a
guess.

## Citations

- Agent permissions and managed resource groups: https://learn.microsoft.com/azure/sre-agent/permissions
- Manage agent permissions (subscription-level Reader): https://learn.microsoft.com/azure/sre-agent/manage-permissions
- Networking permission actions: https://learn.microsoft.com/azure/role-based-access-control/permissions/networking
- Network Watcher RBAC permissions: https://learn.microsoft.com/azure/network-watcher/required-rbac-permissions
- `az network nic`: https://learn.microsoft.com/cli/azure/network/nic
- `az network vnet-gateway`: https://learn.microsoft.com/cli/azure/network/vnet-gateway
- `az network express-route`: https://learn.microsoft.com/cli/azure/network/express-route
- `az network watcher`: https://learn.microsoft.com/cli/azure/network/watcher
- `az account management-group`: https://learn.microsoft.com/cli/azure/account/management-group
- `az resource show`: https://learn.microsoft.com/cli/azure/resource

Analysis only — verify against vendor documentation before applying.
