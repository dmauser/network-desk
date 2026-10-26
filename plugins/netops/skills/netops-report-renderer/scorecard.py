"""NetOps KPI scorecard (deterministic).

Each NetOps engine may return ``result["kpis"]``: a mapping of KPI name -> number. The
scorecard grades every defined KPI as good / warning / critical / unknown against fixed
thresholds and builds a report model for ``render.render_report``. A KPI whose source
skill did not run (or did not report the KPI) is ``unknown``: it is shown, excluded from
the score, and makes the scorecard partial. Nothing is estimated.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_models():
    path = Path(__file__).with_name("models.py")
    spec = spec_from_file_location("netops_report_models", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_models = _load_models()

# (kpi, label, skill, unit, direction, good, warning)
# direction "min": higher is better (value >= good is good, >= warning is warning).
# direction "max": lower is better  (value <= good is good, <= warning is warning).
KPI_DEFINITIONS = (
    ("tunnels_connected_pct", "VPN/ER connections connected", "netops-hybrid-health", "%", "min", 100, 90),
    ("bgp_peers_connected_pct", "BGP peers connected", "netops-hybrid-health", "%", "min", 100, 90),
    ("pe_dns_healthy_pct", "Private endpoints resolving privately", "netops-private-endpoint-dns", "%", "min", 100, 95),
    ("asymmetric_paths", "Asymmetric / blackholed paths", "netops-routing-analyzer", "", "max", 0, 0),
    ("broad_rules", "Overly broad allow rules", "netops-nsg-firewall-audit", "", "max", 0, 5),
    ("risky_mgmt_exposures", "Mgmt ports open to Internet", "netops-exposure-scan", "", "max", 0, 0),
    ("snat_peak_util_pct", "Peak SNAT port utilization", "netops-snat-egress", "%", "max", 70, 85),
    ("subnets_over_threshold", "Subnets above 80% IP utilization", "netops-ip-capacity", "", "max", 0, 2),
    ("flow_log_coverage_pct", "VNets with flow logs", "netops-flow-insights", "%", "min", 100, 80),
)
_POINTS = {"good": 100, "warning": 50, "critical": 0}


def grade(value, direction, good, warning):
    if value is None:
        return "unknown"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("KPI values must be numbers")
    if direction == "min":
        return "good" if value >= good else "warning" if value >= warning else "critical"
    if direction == "max":
        return "good" if value <= good else "warning" if value <= warning else "critical"
    raise ValueError(f"unknown direction {direction!r}")


def compute_scorecard(results):
    """Grade KPIs from a list of engine results. Returns rows, score and unknowns."""

    by_skill = {}
    for result in results or ():
        if not isinstance(result, dict) or not result.get("skill"):
            raise ValueError("each result must be an object with a skill")
        by_skill.setdefault(result["skill"], {}).update(result.get("kpis") or {})
    rows, points, unknown = [], [], []
    for key, label, skill, unit, direction, good, warning in KPI_DEFINITIONS:
        value = by_skill.get(skill, {}).get(key)
        status = grade(value, direction, good, warning)
        if status == "unknown":
            unknown.append(key)
        else:
            points.append(_POINTS[status])
        target = f"{'≥' if direction == 'min' else '≤'} {good}{unit}"
        rows.append({"kpi": key, "label": label, "skill": skill, "status": status,
                     "value": None if value is None else value, "unit": unit, "target": target})
    score = round(sum(points) / len(points)) if points else None
    return {"rows": rows, "score": score, "unknown": unknown,
            "graded": len(points), "total": len(KPI_DEFINITIONS)}


def _fmt(value, unit):
    if value is None:
        return "unknown"
    text = f"{value:.1f}" if isinstance(value, float) and not value.is_integer() else f"{int(value)}"
    return f"{text}{unit}"


def build_scorecard_model(results, *, refreshed_at, scope_summary=None, partial=False,
                          warnings=None, scope_coverage=None):
    """Monthly NetOps KPI scorecard report model."""

    card = compute_scorecard(results)
    findings = [dict(f, skill=f.get("skill") or r["skill"])
                for r in results or () for f in (r.get("findings") or ())]
    base = _models.build_findings_model(
        {"findings": findings,
         "evidence_gaps": [f"{r['skill']}: {g}" for r in results or () for g in r.get("evidence_gaps") or ()],
         "partial": any(r.get("partial") for r in results or ())},
        title="NetOps: Monthly KPI Scorecard",
        description="Network operations health KPIs graded against fixed targets.",
        refreshed_at=refreshed_at, scope_summary=scope_summary, partial=partial,
        warnings=list(warnings or ()) + [f"KPI not measured: {k}" for k in card["unknown"]],
        scope_coverage=scope_coverage)
    tone = ("neutral" if card["score"] is None else "good" if card["score"] >= 90
            else "warning" if card["score"] >= 70 else "critical")
    counts = {s: sum(1 for r in card["rows"] if r["status"] == s)
              for s in ("good", "warning", "critical", "unknown")}
    base["metrics"] = [
        {"label": "NetOps score", "value": "unknown" if card["score"] is None else str(card["score"]),
         "detail": f"{card['graded']} of {card['total']} KPIs graded", "tone": tone},
        {"label": "KPIs on target", "value": str(counts["good"]), "detail": "good", "tone": "good"},
        {"label": "KPIs at risk", "value": str(counts["warning"] + counts["critical"]),
         "detail": f"{counts['critical']} critical",
         "tone": "critical" if counts["critical"] else "warning" if counts["warning"] else "good"},
    ] + base["metrics"]
    base["partial"] = bool(base["partial"] or card["unknown"])
    base["sections"].insert(0, {
        "title": "KPI scorecard",
        "description": "Unknown KPIs are excluded from the score and never estimated.",
        "columns": ["KPI", "Skill", "Value", "Target", "Status"],
        "rows": [[r["label"], r["skill"], _fmt(r["value"], r["unit"]), r["target"], r["status"].upper()]
                 for r in card["rows"]],
        "emptyMessage": "No KPIs defined.",
    })
    return base
