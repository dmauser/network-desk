# Onboarding NetOps for Azure SRE Agent

**NetOps — Network Operations for Azure SRE Agent (powered by Network Desk)** is a read-only Azure
network operations plugin. Two supported paths produce the same result:

- an Azure SRE Agent with the ten NetOps skills (plugin)
- the read-only `netops-investigator` subagent
- scheduled tasks that keep the NetOps Live Reports fresh
- least-privilege, read-only RBAC

Incident response plans are configured separately in the portal (step 7).

| | **Option A: Automated** | **Option B: Manual (portal)** |
|---|---|---|
| Effort | One command, about 10 minutes | About 30–40 minutes of portal steps |
| Creates the agent resource | Yes (Bicep) | You create it in the portal |
| Plugin, subagent, tasks, RBAC | Yes | Step by step below |
| Incident response plans | Manual (step 7) | Manual (step 7) |
| Needs a shell | bash with `az`, `curl`, `python3` | No; Cloud Shell only for optional render steps |

The paths can be mixed. For example, create the agent in the portal, then run the automated script
against it. The script detects the existing agent and adds only what is missing.

## Least-privilege RBAC

NetOps never writes to Azure. Remediation is emitted as a script or IaC for a human to review and
run. The agent identity therefore needs **no write role**. **Network Contributor is not
required.**

| Role | Scope | Why |
|---|---|---|
| [Reader](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/general#reader) | Every managed scope | `az ... show/list` on gateways, connections, VNets, NSGs, Azure Firewall, private endpoints, private DNS zones, public IPs, load balancers and NAT gateways |
| [Monitoring Reader](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/monitor#monitoring-reader) | Every managed scope | `az monitor metrics list` for tunnel, BGP, SNAT, NAT gateway and ExpressRoute metrics |
| [Log Analytics Reader](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/monitor#log-analytics-reader) | Workspaces that hold diagnostics and flow logs | `az monitor log-analytics query` (KQL over `AzureDiagnostics`, `NTANetAnalytics`, and similar tables) |
| **NetOps Network Diagnostics Reader** (custom) | Every managed scope | Only the nine POST-based *read-only* diagnostic actions below |
| Reader | The agent resource itself | Each run reads `knowledgeGraphConfiguration.managedResources` to discover its managed scope |

The custom role is defined in [`deploy/main.bicep`](../../plugins/netops/deploy/main.bicep). Its
actions are exactly `readonly_guard.DIAGNOSTIC_ACTIONS`, and the tests check that the two lists
match:

```text
Microsoft.Network/networkInterfaces/effectiveNetworkSecurityGroups/action
Microsoft.Network/networkInterfaces/effectiveRouteTable/action
Microsoft.Network/networkWatchers/ipFlowVerify/action
Microsoft.Network/networkWatchers/nextHop/action
Microsoft.Network/networkWatchers/securityGroupView/action
Microsoft.Network/networkWatchers/topology/action
Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action
Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action
Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action
```

These are ARM POST operations that return state and change nothing. See
[networking permissions](https://learn.microsoft.com/azure/role-based-access-control/permissions/networking)
and [Network Watcher RBAC](https://learn.microsoft.com/azure/network-watcher/required-rbac-permissions).
Without this role the skills still run. Effective routes, BGP peer status and Network Watcher
results are then reported as evidence gaps rather than findings.

> The portal-created agent also grants **Monitoring Contributor** on the agent's own resource group.
> NetOps does not need it, so `deploy/agent.bicep` omits it.

## What gets deployed

| Component | Detail |
|---|---|
| Resource group | Default `SRE-NetOps-Demo` |
| SRE Agent (`Microsoft.App/agents`) | Default `sre-netops-demo` in `centralus`. Access level Low, Review action mode, model *Automatic*, Stable channel, Limited sandbox egress |
| User-assigned managed identity | Used for actions and the knowledge graph. Managed resources = the subscription |
| Log Analytics + Application Insights | Agent telemetry |
| Agent identity RBAC | The table above |
| Your RBAC | **SRE Agent Administrator** on the agent (data-plane access) |
| Plugin `netops` | `https://github.com/dmauser/network-desk`, path `plugins/netops`, **auto-update on**, 10 skills |
| Subagent `netops-investigator` | Exactly five read-only tools (`RunAzCliReadCommands`, `ExecutePythonCode`, `ListReports`, `GetReport`, `SaveReport`) and the ten NetOps skills |
| Scheduled tasks | Six tasks (below), **Autonomous**, response agent `netops-investigator` |

| Task id | Name | Cron (UTC) | Live Report |
|---|---|---|---|
| `hybrid-health` | NetOps: Hybrid Connectivity Health (Daily) | `0 6 * * *` | NetOps: Hybrid Health |
| `nsg-firewall-audit` | NetOps: NSG & Firewall Audit (Weekly) | `0 7 * * 1` | NetOps: NSG & Firewall Audit |
| `pe-dns-validation` | NetOps: Private Endpoint DNS Validation (Weekly) | `30 7 * * 1` | NetOps: Private Endpoint DNS |
| `exposure-scan` | NetOps: Exposure Scan (Weekly) | `0 8 * * 1` | NetOps: Exposure |
| `capacity-forecast` | NetOps: IP & Gateway Capacity Forecast (Monthly) | `0 7 1 * *` | NetOps: IP & Gateway Capacity |
| `kpi-scorecard` | NetOps: Monthly Review (KPI Scorecard) | `0 9 1 * *` | NetOps: Monthly Review |

**Why the tasks are Autonomous.** Scheduled tasks run unattended. In
[Review mode](https://learn.microsoft.com/azure/sre-agent/run-modes), a run waits for approval
before any write action, which can stall an unattended run. NetOps has no write tools, so
Autonomous mode adds no write capability; it only lets reports refresh. Incident response plans
use **Review** (step 7).

> A Live Report refreshes only while its scheduled task exists and is Active.

---

## Option A: Automated

Prerequisites:

- `az login` as an identity with **Owner** on the subscription, or Contributor plus User Access
  Administrator. Creating the custom role needs `Microsoft.Authorization/roleDefinitions/write`.
- A bash shell with `az`, `curl` and `python3`: WSL, Linux, macOS, or Azure Cloud Shell.
- In Cloud Shell, first run `az login --scope https://azuresre.dev/.default`.

```bash
git clone https://github.com/dmauser/network-desk
cd network-desk
./plugins/netops/deploy/deploy.sh
```

The script prompts for the agent name, region and resource group. Press Enter to keep each
default. It then runs two phases:

1. **Infrastructure.** [`main.bicep`](../../plugins/netops/deploy/main.bicep) and
   [`agent.bicep`](../../plugins/netops/deploy/agent.bicep) create the resource group, identity,
   monitoring, the agent, the custom diagnostics role and the read-only grants.
2. **Agent configuration.** [`install-api.sh`](../../plugins/netops/install-api.sh) runs with
   `PLUGIN_SOURCE=direct`. It installs the plugin from the GitHub URL with auto-update on, upserts
   `netops-investigator`, and creates the scheduled tasks.

Re-running is safe. An existing agent is never re-provisioned, and phase 2 only upserts.

### Options

| Flag / variable | Default | Purpose |
|---|---|---|
| `-n` / `SRE_AGENT_NAME` | `sre-netops-demo` | Agent name |
| `-l` / `LOCATION` | `centralus` | A region that supports SRE Agent |
| `-g` / `RESOURCE_GROUP` | `SRE-NetOps-Demo` | Resource group, created if missing |
| `-s` / `SUBSCRIPTION_ID` | current `az` subscription | Target subscription |
| `--tasks` / `TASK_IDS` | `all` | Comma-separated task ids (see the table above) |
| `HYBRID_CRON`, `NSG_AUDIT_CRON`, `PEDNS_CRON`, `EXPOSURE_CRON`, `CAPACITY_CRON`, `SCORECARD_CRON` | manifest default | Per-task schedule override (UTC) |
| `ALERT_EMAIL` | unset | Email delivery. Hybrid health emails only on critical or high findings |
| `NETOPS_KUSTO_TOOL` | unset | Name of an existing custom Kusto tool (created in the portal) to add to the subagent |
| `REPO_SLUG` / `GITHUB_PAT` | `dmauser/network-desk` / unset | Install from a fork or a private fork |
| `FORCE_INFRA=1` | off | Re-run Bicep even though the agent exists |
| `-y` | prompt | Accept defaults without prompting |
| `--dry-run` | | Validate inputs and the template; change nothing |

```bash
# Hybrid health only, non-interactive, existing agent
./plugins/netops/deploy/deploy.sh -y -n contoso-sre -g rg-sre --tasks hybrid-health

# Validate only
./plugins/netops/deploy/deploy.sh --dry-run
```

**Already have an agent and don't want Bicep?** Run only phase 2:

```bash
AGENT_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/agents/<name> \
MI_OBJECT_ID=<agent UAMI principalId> \
  ./plugins/netops/install-api.sh
```

With `MI_OBJECT_ID` set, the installer grants Reader, Monitoring Reader and Log Analytics Reader on
every managed scope. It also grants the diagnostics role when that role exists in the subscription.

---

## Option B: Manual (portal)

### 1. Create the agent

1. In the Azure portal, search for **Azure SRE Agent** and select **Create**.
2. Set the resource group, agent name and region, and create a new Application Insights resource.
3. When the agent reaches **Succeeded**, open it at [sre.azure.com](https://sre.azure.com) and add
   the subscriptions or resource groups to analyze under **managed resources**. Every NetOps skill
   is bounded by this list, and scheduled runs fail closed without it.

### 2. Grant read-only access

Assign the following roles to the agent's **user-assigned** managed identity, which is listed on
the agent's Identity blade.

1. On each managed subscription or resource group, go to **Access control (IAM) → Add role
   assignment**. Assign **Reader**, **Monitoring Reader** and **Log Analytics Reader**.
2. On the agent resource's **Access control (IAM)**, assign **Reader**.
3. Optional but recommended: create the custom diagnostics role, then assign it on the managed
   scopes.
   - You can create it
     [in the portal](https://learn.microsoft.com/azure/role-based-access-control/custom-roles-portal)
     with exactly the nine actions above.
   - Or deploy it with `az deployment sub create -f plugins/netops/deploy/main.bicep ...`.
4. Do **not** assign Network Contributor, Contributor or Monitoring Contributor.

### 3. Install the plugin (skills)

In sre.azure.com, go to **Builder → Plugins → Install from URL**:

| Field | Value |
|---|---|
| Source URL | `https://github.com/dmauser/network-desk` (or your fork) |
| Path in repo | `plugins/netops` |
| Auto-update | **On** |

Wait for the success message reporting 10 skills. A plugin carries **only skills**, so continue
with steps 4 and 5.

### 4. Create the `netops-investigator` subagent

1. Render the YAML with your agent's resource ID:

   ```bash
   python3 plugins/netops/agents/render_agent_yaml.py \
     --agent-resource-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/agents/<name> \
     > netops-investigator.yaml
   ```

2. In **Agent Canvas → Create → Custom agent → YAML**, paste the file and select **Create**.
3. Confirm that **Tools** lists exactly `RunAzCliReadCommands`, `ExecutePythonCode`, `ListReports`,
   `GetReport` and `SaveReport`. An empty tool list inherits every tool, including write tools.

### 5. Create the scheduled tasks

1. Render the exact task definitions:

   ```bash
   TASK_AGENT_NAME=netops-investigator TASK_IDS=all \
   AGENT_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/agents/<name> \
   python3 plugins/netops/scheduled-tasks/render_tasks.py api > netops-tasks.json
   ```

2. For each task, go to **Scheduled tasks → Create scheduled task** and copy the rendered fields:
   - **name**
   - **agentPrompt**, pasted unedited
   - **custom cron** (UTC)
   - **Response custom agent**: `netops-investigator`
   - **Agent autonomy level**: **Autonomous**
   - Leave the date range and run limit unset.

### 6. Verify

1. Select **Run now** on `NetOps: Hybrid Connectivity Health (Daily)`.
2. Open **Operations Hub → Live Reports → NetOps: Hybrid Health** and check **Refreshed**.
3. In chat, type `/agent`, select `netops-investigator`, and ask:
   *"Branch users can't reach Azure; is the VPN tunnel down?"*

### 7. Incident response plans (both paths)

Create the four plans in [`response-plans/`](../../plugins/netops/response-plans/README.md) in the
portal, each with autonomy **Review**, then delete the quickstart plan. To print the portal fields
or the `azmcp` command for each plan, run:

```bash
python3 plugins/netops/response-plans/validate_plans.py portal
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `deploy.sh`: *data plane still returns HTTP 403* | The SRE Agent Administrator role can take minutes to propagate. Re-run the script. |
| Cannot get an `https://azuresre.dev` token | In Cloud Shell, run `az login --scope https://azuresre.dev/.default`. |
| A scheduled run reports *managed scope unavailable* | Add managed resources to the agent, and grant the agent identity Reader on the agent resource. |
| Effective routes, BGP status or Network Watcher results appear as **evidence gaps** | The custom **NetOps Network Diagnostics Reader** role is missing on that scope. |
| Flow insights are empty | VNet flow logs or a Traffic Analytics workspace are missing, or Log Analytics Reader is missing on that workspace. |
| A report never refreshes | The task is missing, paused, in **Review** mode, or has a run limit. |
| `netops-investigator` is missing from `/agent` | Hard-refresh (Ctrl+F5) and start a **New chat**. |
