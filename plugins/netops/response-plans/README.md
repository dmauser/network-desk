# NetOps incident response plans

Azure SRE Agent [incident response plans](https://learn.microsoft.com/azure/sre-agent/incident-response-plans)
route incoming incidents to a custom agent based on a filter. Each plan has two parts: an **incident filter**
and a **custom agent handler**. NetOps ships four plan specs that route Azure Monitor alerts to
`netops-investigator` in **Review** mode.

> The YAML files here are **specs**, not an import format. SRE Agent has no file import for response plans.
> A human creates them in the portal ([steps](https://learn.microsoft.com/azure/sre-agent/response-plan)) or
> with `azmcp sreagent incidents plans create`
> ([Azure MCP reference](https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/azure-sre-agent)).
> `validate_plans.py` validates the specs in CI and prints both forms.

| Plan | Severity | Title contains | Primary skill | Follow-ups |
| --- | --- | --- | --- | --- |
| [Hybrid connectivity down](hybrid-connectivity-down.yaml) | Sev0, Sev1 | `netops-hybrid` | netops-hybrid-health | netops-routing-analyzer |
| [PaaS unreachable via private endpoint](paas-unreachable-private-endpoint.yaml) | Sev1, Sev2 | `netops-pe` | netops-private-endpoint-dns | netops-routing-analyzer, netops-nsg-firewall-audit |
| [Latency, packet drops or SNAT exhaustion](latency-drops-snat.yaml) | Sev1, Sev2 | `netops-egress` | netops-snat-egress | netops-flow-insights, netops-routing-analyzer |
| [Asymmetric routing through NVA](asymmetric-routing-nva.yaml) | Sev1, Sev2 | `netops-routing` | netops-routing-analyzer | netops-flow-insights, netops-nsg-firewall-audit |

## Why Review, never Autonomous

New portal plans default to **Autonomous**, which lets the agent perform mitigation with whatever permissions
it has. NetOps is read-only by design: the agent holds only read roles plus the NetOps diagnostic role, and it
proposes remediation as a script for a human to run. Always pick **Review**. `validate_plans.py check` rejects
any other autonomy value.

## Alert naming convention

For Azure Monitor, a plan filters on **Severity** plus an optional **Title contains** keyword. Put the plan
keyword (for example `netops-hybrid`) in the alert rule name so that only network alerts reach
`netops-investigator`. Each spec's `alertSignals` lists suggested metric alerts. Every metric name is verified
on the cited Azure Monitor supported-metrics page.

## Create the plans in the portal

1. Connect Azure Monitor as the incident platform
   ([Azure Monitor alerts](https://learn.microsoft.com/azure/sre-agent/azure-monitor-alerts)).
2. **Delete the quickstart plan**: go to **Builder > Incident response plans > Table view**. Otherwise the
   quickstart plan (Sev0–Sev2, Autonomous) runs alongside these plans and can double-process incidents.
3. Print the field values:

   ```bash
   python plugins/netops/response-plans/validate_plans.py portal
   ```

4. For each plan, go to **Builder > Agent Canvas > Create > Trigger > Incident response plan**. Then enter:
   - the name, severity levels and title keyword;
   - **Response custom agent** `netops-investigator`;
   - **Agent autonomy level** **Review**;
   - **Reinvestigation cooldown** on, 3 hours.
5. Select **Next** to preview matching incidents, then select **Create**. The plan shows **Status On**.
6. To test safely, create an alert whose title contains the keyword plus `[TEST]`, then confirm the thread
   is routed to `netops-investigator`.

## Create the plans with Azure MCP (optional, human-run)

```bash
python plugins/netops/response-plans/validate_plans.py azmcp --agent <sre-agent-name> --resource-group <rg>
```

The command prints one `azmcp sreagent incidents plans create ... --agent-mode review` line per plan, for you
to review and run. Azure MCP takes an abstract severity (`critical|high|medium|low`), a trigger condition and
steps, not the portal's Azure Monitor Sev filter. Use the portal when you need exact Sev and title filters.
The SRE Agent never creates or changes plans.

## Validate

```bash
python plugins/netops/response-plans/validate_plans.py check
```

The check validates each spec against [`schema.json`](schema.json) and then applies these semantic rules:

- every skill exists in `agents/routing.json`;
- the first step resolves the managed scope;
- one step renders the report with `netops-report-renderer`;
- no step contains a write command or a `;` (the azmcp step separator);
- every metric is on the verified list;
- plan names and title keywords are unique.

Analysis only - verify against vendor documentation before applying.
