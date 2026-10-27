# NetOps — Network Operations for Azure SRE Agent (powered by Network Desk)

NetOps is an [Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/overview) plugin
for **read-only operations on live Azure networks**. It ships ten skills, the
`netops-investigator` subagent, six scheduled tasks and four incident response plan specs.

| | Network Desk (Copilot CLI extension) | NetOps (this plugin) |
| --- | --- | --- |
| Purpose | Design-time advisory | Runtime operations and triage |
| Clouds | Azure, AWS, GCP, 14 firewall vendors | Azure only |
| Data | No live data; docs MCP validation | Live Azure via `RunAzCliReadCommands` and KQL |
| Runs | Interactively in Copilot CLI | Interactive chat, scheduled tasks, incident response plans |

Specialist knowledge has a single source of truth: `extensions/network-desk/registry.mjs` and
`extensions/network-desk/specialists/**`. `scripts/netops/build-netops.mjs` generates each
skill's `reference/` folder from them. Don't hand-edit `reference/`.

## Read-only by design

- The agent executes no Azure writes and has no write RBAC. It uses only `RunAzCliReadCommands`
  (list/show reads, the documented diagnostic actions and `az monitor log-analytics query`) and
  sandbox Python.
- Remediation is always a generated script or IaC with its change commands **commented out**.
  A human reviews and runs it. The agent never executes it.
- Every skill and scheduled task enforces **managed scope** (`netops-managed-scope`), with the same
  semantics as the FinOps pack:
  - Scope is read live from the agent's `properties.knowledgeGraphConfiguration.managedResources`.
  - Scheduled tasks fail closed.
  - Interactive out-of-scope requests need explicit user confirmation in a later turn.

See [least-privilege RBAC](../../docs/netops/ONBOARDING.md#least-privilege-rbac). The required
roles are Reader, Monitoring Reader, Log Analytics Reader and the custom
*NetOps Network Diagnostics Reader* role, which grants 9 read-only diagnostic actions.
Network Contributor is **not** required.

## Skills

Each skill contains:
- `SKILL.md`: when to use, inputs, exact az/KQL steps, interpretation, output schema and Microsoft Learn citations.
- A deterministic Python engine.
- `examples/` fixtures.
- Generated `reference/` content.

| Skill | Network Desk source | Engine | Purpose |
| --- | --- | --- | --- |
| `netops-managed-scope` | FinOps pack | `scope.py` | Scope discovery and enforcement |
| `netops-report-renderer` | FinOps pack + report builder | `render.py` | Deterministic Live Report rendering |
| `netops-hybrid-health` | Hybrid Connectivity | `hybrid.py` | VPN/ExpressRoute gateways, BGP state, flaps, route counts, tunnels |
| `netops-private-endpoint-dns` | Private Link + DNS | `pedns.py` | PE status, private DNS zone links/records, resolution |
| `netops-routing-analyzer` | Troubleshooting + VNet | `routing.py` | Effective routes, UDRs, peering, asymmetric NVA/firewall paths |
| `netops-nsg-firewall-audit` | Network Security + Firewall | `ruleaudit.py` | Broad, shadowed and unused rules; risky management ports |
| `netops-exposure-scan` | Network Security | `exposure.py` | Public IPs, open ports, PaaS public access, missing WAF |
| `netops-snat-egress` | Troubleshooting + Monitoring | `snat.py` | LB/NAT Gateway SNAT exhaustion, egress health |
| `netops-ip-capacity` | Capacity + VNet | `capacity.py` | Subnet IP exhaustion forecast, gateway capacity |
| `netops-flow-insights` | Monitoring | `flows.py` | VNet/NSG flow logs and Traffic Analytics (`NTANetAnalytics`) |

## Agent: `netops-investigator`

`agents/netops-investigator.yaml` and `.json` are rendered by `render_agent_yaml.py` from
`routing.json`. The agent:
1. Routes a symptom to the first matching skill, using Network Desk's routing.
2. Chains to follow-up skills when the evidence points elsewhere.
3. Runs each skill's engine and produces an evidence-based triage report.

Tools: `RunAzCliReadCommands`, `ExecutePythonCode`, `ListReports`, `GetReport`, `SaveReport`.
You can add a Kusto tool with `NETOPS_KUSTO_TOOL`.

## Scheduled tasks

| Task | Cadence (default cron, UTC) | Skill(s) |
| --- | --- | --- |
| Hybrid Connectivity Health | Daily `0 6 * * *` (emails only on critical/high) | hybrid-health |
| NSG & Firewall Audit | Weekly `0 7 * * 1` | nsg-firewall-audit |
| Private Endpoint DNS Validation | Weekly `30 7 * * 1` | private-endpoint-dns |
| Exposure Scan | Weekly `0 8 * * 1` | exposure-scan |
| IP & Gateway Capacity Forecast | Monthly `0 7 1 * *` | ip-capacity |
| Monthly Review (KPI Scorecard) | Monthly `0 9 1 * *` | all |

`scheduled-tasks/task-manifest.json` and `prompts/*.txt` are the source. Every prompt begins with
the strict managed-scope preamble `prompts/_managed-scope.txt`. `render_tasks.py` generates the
YAMLs.

Tasks run in **autonomous** mode. They have no write tools, and in Review mode a task would
stall waiting for write approval
([run modes](https://learn.microsoft.com/azure/sre-agent/run-modes)).

## Incident response plans

The specs are in `response-plans/*.yaml` and are validated by `validate_plans.py` against
`schema.json`:

- Hybrid connectivity down (VPN/ER)
- PaaS unreachable via private endpoint
- Latency / packet drops / SNAT exhaustion
- Asymmetric routing through an NVA

Configure these in the portal with autonomy **Review**
([incident response plans](https://learn.microsoft.com/azure/sre-agent/incident-response-plans)).
See [`response-plans/README.md`](response-plans/README.md).

## Install

See [docs/netops/ONBOARDING.md](../../docs/netops/ONBOARDING.md):

- **Option A: Automated.** `deploy/deploy.sh` deploys the agent (Bicep), the read-only role
  assignments and the custom role, then runs `install-api.sh` to import the plugin, agent and
  tasks.
- **Option B: Manual (portal).** Add the `network-desk` marketplace, install `netops`, create the
  subagent and the tasks.

A plugin install alone imports only the skills. The agent and tasks come from `install-api.sh`
or the portal steps.

## Development

```bash
node scripts/netops/build-netops.mjs [--check]                # regenerate skills/*/reference/
python plugins/netops/scheduled-tasks/render_tasks.py write|check
python plugins/netops/agents/render_agent_yaml.py write|check
python plugins/netops/response-plans/validate_plans.py check
python -m pytest -q tests/netops evals/netops                 # unit, manifest, scope, deploy tests
python evals/netops/run.py                                    # fault-scenario evals
```

`evals/netops/fixtures/` holds fault scenarios modeled on
[azure-sre-netops](https://github.com/dmauser/azure-sre-netops) (SC-xx) and
[az-srenetops-microhack](https://github.com/dmauser/az-srenetops-microhack) (MH-xx). Each one
specifies the injected fault, the expected skill routing and the expected finding.

Analysis only — verify against vendor documentation before applying.
