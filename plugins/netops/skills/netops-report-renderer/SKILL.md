---
name: netops-report-renderer
description: Deterministically renders static NetOps Live Report HTML from structured NetOps engine results. Common finding schema, per-skill adapters, investigator triage report and monthly KPI scorecard; CSP-compliant, nonce-safe, escaped HTML (render.py copied from FinOps). Performs no Azure or connector calls.
---

## Purpose

Use this utility after a NetOps engine (`hybrid.py`, `pedns.py`, ...) has produced its
result. Build a model with the matching adapter in `models.py` (or `scorecard.py`), call
`write_report` from `render.py`, then pass the path to `SaveReport` with
`allowedTools: []`.

The renderer owns HTML escaping, CSP, nonce placement, Chart.js SRI, empty states,
partial-data warnings, and stable layout. Do not ask the model to regenerate or rewrite the
HTML. Adapters do no I/O, read no clock and never mutate input; supply `refreshed_at`.

Every saved report is a **static snapshot**. It refreshes only when a scheduled task (or a
user) runs the analysis again. When a user asks for a report from chat, say so and point
them to the NetOps scheduled tasks.

## Common result and finding schema

Every NetOps engine returns:

```json
{
  "skill": "netops-hybrid-health",
  "findings": [{
    "id": "HYB-BGP-NOT-CONNECTED:vpngw-hub:10.100.0.4",
    "skill": "netops-hybrid-health",
    "severity": "critical | high | medium | low | info",
    "resource_id": "/subscriptions/.../virtualNetworkGateways/vpngw-hub",
    "title": "BGP peer 10.100.0.4 is not Connected",
    "evidence": "state=Connecting ...",
    "recommendation": "What a human should do",
    "remediation_script": "az ...   # HUMAN-RUN ONLY, never executed by the agent",
    "citations": ["https://learn.microsoft.com/..."]
  }],
  "evidence_gaps": ["BGP peer status unavailable: RunAzCliReadCommands rejected POST"],
  "metrics": [{"label": "...", "value": "...", "detail": "...", "tone": "good"}],
  "kpis": {"bgp_peers_connected_pct": 100.0},
  "partial": false,
  "warnings": []
}
```

Finding IDs are deterministic and unique. Any evidence gap marks the report partial; gaps
are listed, never filled with guesses.

## Adapter API

```python
from models import (
    build_hybrid_health_model, build_private_endpoint_dns_model,
    build_routing_analyzer_model, build_nsg_firewall_audit_model,
    build_exposure_scan_model, build_snat_egress_model,
    build_ip_capacity_model, build_flow_insights_model,
    build_triage_model, ADAPTERS,
)
from scorecard import build_scorecard_model
from render import write_report

model = build_hybrid_health_model(
    result,
    refreshed_at="2026-10-26T06:00:00Z",
    scope_summary=["/subscriptions/.../resourceGroups/rg-hub"],
    partial=False,
    warnings=[],
    scope_coverage=[{"scope": "/subscriptions/.../resourceGroups/rg-hub", "status": "complete",
                     "included": 12, "excluded": 0, "unattributed": 0}],
)
path = write_report(model, "netops-hybrid-health.html")
```

All adapters share the keyword-only context arguments
`(*, refreshed_at, scope_summary=None, partial=False, warnings=None, scope_coverage=None)`.
A `filter_resources` result (from `netops-managed-scope`) can be passed as a coverage row
after adding `scope` and `status`; its `*_count` fields are read directly.

| Adapter | Input |
| --- | --- |
| `build_<skill>_model(result, ...)` | One engine result for that skill (or a bare list of findings). |
| `build_triage_model(results, *, symptom, routed_skills, ...)` | List of engine results produced during an investigator triage. |
| `build_scorecard_model(results, ...)` | List of engine results; grades `KPI_DEFINITIONS` (good / warning / critical / unknown). Unknown KPIs are excluded from the score and make the report partial. |

Report sections: Findings, Remediation scripts (human review required), Evidence gaps,
Scope coverage, Citations; the scorecard adds a KPI table first. Every report description
ends with the NetOps disclaimer.

## Rendering API

- `render_report(model) -> str` — validate and return deterministic static HTML.
- `write_report(model, output_path) -> str` — write UTF-8 HTML and return the path.

Keep `allowedTools: []` when saving. No connector calls, no view-time data fetching.

Analysis only — verify against vendor documentation before applying.
