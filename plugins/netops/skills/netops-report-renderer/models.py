"""Deterministic report-model adapters for NetOps skills.

Every NetOps analysis engine returns the same result envelope::

    {
      "skill": "netops-hybrid-health",
      "findings": [<finding>, ...],
      "evidence_gaps": ["text", ...],     # optional: data that could not be read
      "metrics": [{"label", "value", "detail", "tone"}],  # optional, pre-formatted
      "kpis": {"name": number},           # optional, consumed by scorecard.py
      "partial": False, "warnings": [],   # optional
    }

and every finding has the common schema::

    {
      "id": "HYB-BGP-DOWN:<resource>",    # stable, deterministic
      "skill": "netops-hybrid-health",
      "severity": "critical|high|medium|low|info",
      "resource_id": "/subscriptions/...",  # may be "" for scope-level findings
      "title": "BGP peer 10.2.0.4 is not Connected",
      "evidence": "state=Connecting; ...",   # str or JSON-serializable dict
      "recommendation": "Human action to take",
      "remediation_script": "az ...",     # optional; HUMAN-RUN ONLY, never executed
      "citations": ["https://learn.microsoft.com/..."],
    }

Adapters do no I/O, read no clock, make no network calls and never mutate input. They
return the generic model accepted by ``render.render_report``.
"""

from __future__ import annotations

import json

SEVERITIES = ("critical", "high", "medium", "low", "info")
_SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}
_TONES = {"neutral", "good", "warning", "critical"}
DISCLAIMER = (
    "Analysis only — verify against vendor documentation before applying. "
    "NetOps is read-only: remediation scripts are for human review and are never executed by the agent."
)

SKILL_REPORTS = {
    "netops-hybrid-health": ("NetOps: Hybrid Connectivity Health",
                             "VPN / ExpressRoute gateway, connection, BGP and route-count health."),
    "netops-private-endpoint-dns": ("NetOps: Private Endpoint & DNS Validation",
                                    "Private endpoint connection state, private DNS zone links and records."),
    "netops-routing-analyzer": ("NetOps: Routing Analysis",
                                "Effective routes, UDRs, next hops and asymmetric routing through NVAs/firewalls."),
    "netops-nsg-firewall-audit": ("NetOps: NSG & Firewall Rule Audit",
                                  "Overly broad, shadowed and risky NSG / Azure Firewall rules."),
    "netops-exposure-scan": ("NetOps: Exposure Scan",
                             "Public IPs, internet-open ports, PaaS public network access and WAF coverage."),
    "netops-snat-egress": ("NetOps: SNAT & Egress Health",
                           "SNAT port usage on Load Balancer / NAT Gateway and egress health."),
    "netops-ip-capacity": ("NetOps: IP & Gateway Capacity Forecast",
                           "Subnet IP exhaustion forecast and gateway capacity."),
    "netops-flow-insights": ("NetOps: Flow Insights",
                             "VNet / NSG flow logs and Traffic Analytics insights."),
}


# --- validation ---------------------------------------------------------------------

def _text(value):
    return "" if value is None else str(value)


def _sorted_unique(values):
    unique = {}
    for value in values or ():
        text = _text(value).strip()
        if text:
            unique.setdefault(text, text)
    return sorted(unique)


def normalize_finding(finding, *, default_skill=None):
    """Validate one finding and return a normalized copy (input is not mutated)."""

    if not isinstance(finding, dict):
        raise ValueError("finding must be an object")
    severity = _text(finding.get("severity")).strip().lower()
    if severity not in _SEVERITY_RANK:
        raise ValueError(f"finding severity {finding.get('severity')!r} is invalid")
    skill = _text(finding.get("skill") or default_skill).strip()
    fid = _text(finding.get("id")).strip()
    title = _text(finding.get("title")).strip()
    for field, value in (("id", fid), ("skill", skill), ("title", title)):
        if not value:
            raise ValueError(f"finding {field} is required")
    evidence = finding.get("evidence")
    if isinstance(evidence, (dict, list)):
        evidence = json.dumps(evidence, sort_keys=True, separators=(", ", "="))
    citations = finding.get("citations") or []
    if not isinstance(citations, list):
        raise ValueError("finding citations must be an array")
    return {
        "id": fid,
        "skill": skill,
        "severity": severity,
        "resource_id": _text(finding.get("resource_id")).strip(),
        "title": title,
        "evidence": _text(evidence),
        "recommendation": _text(finding.get("recommendation")),
        "remediation_script": _text(finding.get("remediation_script")),
        "citations": _sorted_unique(citations),
    }


def sort_findings(findings):
    """Stable order: severity, skill, resource, id."""

    return sorted(
        findings,
        key=lambda f: (_SEVERITY_RANK[f["severity"]], f["skill"],
                       f["resource_id"].casefold(), f["id"]),
    )


def severity_counts(findings):
    counts = {name: 0 for name in SEVERITIES}
    for finding in findings:
        counts[finding["severity"]] += 1
    return counts


def _short_resource(resource_id):
    if not resource_id:
        return "(scope)"
    parts = resource_id.rstrip("/").split("/")
    return parts[-1] if parts else resource_id


def _coverage_rows(scope_coverage):
    rows = []
    for item in scope_coverage or ():
        if not isinstance(item, dict):
            raise ValueError("scope_coverage rows must be objects")
        for field in ("included", "excluded", "unattributed"):
            value = item.get(field, item.get(f"{field}_count", 0))
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"scope_coverage.{field} must be an integer")
        rows.append([
            _text(item.get("scope")),
            _text(item.get("status") or "complete"),
            str(item.get("included", item.get("included_count", 0))),
            str(item.get("excluded", item.get("excluded_count", 0))),
            str(item.get("unattributed", item.get("unattributed_count", 0))),
            _text(item.get("detail")),
        ])
    return sorted(rows)


def _metric_list(metrics):
    out = []
    for metric in metrics or ():
        if not isinstance(metric, dict):
            raise ValueError("metrics must be objects")
        tone = _text(metric.get("tone") or "neutral").lower()
        if tone not in _TONES:
            raise ValueError(f"metric tone {tone!r} is invalid")
        out.append({"label": _text(metric.get("label")), "value": _text(metric.get("value")),
                    "detail": _text(metric.get("detail")), "tone": tone})
    return out


# --- adapters -----------------------------------------------------------------------

def build_findings_model(result, *, title, description, refreshed_at, scope_summary=None,
                         partial=False, warnings=None, scope_coverage=None):
    """Generic findings report used by every per-skill adapter."""

    if not _text(refreshed_at).strip():
        raise ValueError("refreshed_at is required")
    if isinstance(result, list):
        result = {"findings": result}
    if not isinstance(result, dict):
        raise ValueError("result must be an object or a list of findings")
    default_skill = result.get("skill")
    findings = sort_findings(
        [normalize_finding(f, default_skill=default_skill) for f in result.get("findings") or ()]
    )
    seen = set()
    for finding in findings:
        if finding["id"] in seen:
            raise ValueError(f"duplicate finding id {finding['id']!r}")
        seen.add(finding["id"])
    gaps = _sorted_unique(result.get("evidence_gaps"))
    all_warnings = _sorted_unique(list(warnings or ()) + list(result.get("warnings") or ())
                                  + [f"Evidence gap: {gap}" for gap in gaps])
    coverage = list(scope_coverage or ()) + list(result.get("scope_coverage") or ())
    is_partial = bool(partial or result.get("partial") or gaps
                      or any(isinstance(c, dict) and c.get("partial") for c in coverage))
    counts = severity_counts(findings)

    metrics = [
        {"label": "Findings", "value": str(len(findings)),
         "detail": f"{counts['info']} informational", "tone": "neutral"},
        {"label": "Critical", "value": str(counts["critical"]), "detail": "Act now",
         "tone": "critical" if counts["critical"] else "good"},
        {"label": "High", "value": str(counts["high"]), "detail": "Act this week",
         "tone": "warning" if counts["high"] else "good"},
        {"label": "Medium / Low", "value": f"{counts['medium']} / {counts['low']}",
         "detail": "Plan", "tone": "neutral"},
    ] + _metric_list(result.get("metrics"))

    chart = {
        "type": "doughnut", "label": "Findings by severity", "title": "Findings by severity",
        "labels": [s.title() for s in SEVERITIES if counts[s]],
        "values": [counts[s] for s in SEVERITIES if counts[s]],
    }

    sections = [
        {
            "title": "Findings",
            "description": "Ordered by severity. Evidence is quoted from read-only Azure data.",
            "columns": ["Severity", "Skill", "Resource", "Finding", "Evidence", "Recommendation"],
            "rows": [[f["severity"].upper(), f["skill"], _short_resource(f["resource_id"]),
                      f["title"], f["evidence"], f["recommendation"]] for f in findings],
            "emptyMessage": "No findings in the managed scope.",
        },
        {
            "title": "Remediation scripts (human review required)",
            "description": "Generated for a human operator to review, adapt and run. NetOps never executes them.",
            "columns": ["Finding", "Resource", "Script"],
            "rows": [[f["id"], f["resource_id"] or "(scope)", f["remediation_script"]]
                     for f in findings if f["remediation_script"]],
            "emptyMessage": "No remediation scripts were generated.",
        },
        {
            "title": "Evidence gaps",
            "description": "Sources that could not be read. Conclusions that depend on them are unknown.",
            "columns": ["Gap"],
            "rows": [[gap] for gap in gaps],
            "emptyMessage": "No evidence gaps.",
        },
        {
            "title": "Scope coverage",
            "description": "Resources inside, outside and unattributable to the managed scope.",
            "columns": ["Scope", "Status", "Included", "Excluded", "Unattributed", "Detail"],
            "rows": _coverage_rows(coverage),
            "emptyMessage": "No scope coverage rows were supplied.",
        },
        {
            "title": "Citations",
            "description": "Microsoft Learn sources for the checks above.",
            "columns": ["URL"],
            "rows": [[url] for url in _sorted_unique(c for f in findings for c in f["citations"])],
            "emptyMessage": "No citations.",
        },
    ]
    return {
        "title": _text(title),
        "description": f"{_text(description)} {DISCLAIMER}".strip(),
        "refreshedAt": _text(refreshed_at),
        "scopeSummary": _sorted_unique(list(scope_summary or ()) + list(result.get("scope_summary") or ())),
        "partial": is_partial,
        "warnings": all_warnings,
        "metrics": metrics,
        "chart": chart,
        "sections": sections,
    }


def _skill_adapter(skill):
    title, description = SKILL_REPORTS[skill]

    def adapter(result, *, refreshed_at, scope_summary=None, partial=False, warnings=None,
                scope_coverage=None):
        if isinstance(result, dict) and result.get("skill") not in (None, skill):
            raise ValueError(f"result is for {result.get('skill')!r}, expected {skill!r}")
        if isinstance(result, dict) and "skill" not in result:
            result = dict(result, skill=skill)
        if isinstance(result, list):
            result = {"skill": skill, "findings": result}
        return build_findings_model(result, title=title, description=description,
                                    refreshed_at=refreshed_at, scope_summary=scope_summary,
                                    partial=partial, warnings=warnings,
                                    scope_coverage=scope_coverage)

    adapter.__name__ = "build_" + skill.removeprefix("netops-").replace("-", "_") + "_model"
    adapter.__doc__ = f"Report model for {skill}."
    return adapter


build_hybrid_health_model = _skill_adapter("netops-hybrid-health")
build_private_endpoint_dns_model = _skill_adapter("netops-private-endpoint-dns")
build_routing_analyzer_model = _skill_adapter("netops-routing-analyzer")
build_nsg_firewall_audit_model = _skill_adapter("netops-nsg-firewall-audit")
build_exposure_scan_model = _skill_adapter("netops-exposure-scan")
build_snat_egress_model = _skill_adapter("netops-snat-egress")
build_ip_capacity_model = _skill_adapter("netops-ip-capacity")
build_flow_insights_model = _skill_adapter("netops-flow-insights")

ADAPTERS = {
    "netops-hybrid-health": build_hybrid_health_model,
    "netops-private-endpoint-dns": build_private_endpoint_dns_model,
    "netops-routing-analyzer": build_routing_analyzer_model,
    "netops-nsg-firewall-audit": build_nsg_firewall_audit_model,
    "netops-exposure-scan": build_exposure_scan_model,
    "netops-snat-egress": build_snat_egress_model,
    "netops-ip-capacity": build_ip_capacity_model,
    "netops-flow-insights": build_flow_insights_model,
}


def build_triage_model(results, *, symptom, routed_skills, refreshed_at, scope_summary=None,
                       partial=False, warnings=None, scope_coverage=None):
    """Investigator triage report: merged findings from every skill that ran."""

    if not isinstance(results, list):
        raise ValueError("results must be a list of skill results")
    merged = {"findings": [], "evidence_gaps": [], "warnings": [], "partial": False}
    for result in results:
        if not isinstance(result, dict) or not result.get("skill"):
            raise ValueError("each triage result must be an object with a skill")
        merged["findings"].extend(dict(f, skill=f.get("skill") or result["skill"])
                                  for f in result.get("findings") or ())
        merged["evidence_gaps"].extend(f"{result['skill']}: {gap}"
                                       for gap in result.get("evidence_gaps") or ())
        merged["warnings"].extend(result.get("warnings") or ())
        merged["partial"] = merged["partial"] or bool(result.get("partial"))
    model = build_findings_model(
        merged, title="NetOps: Incident Triage",
        description=f"Symptom: {_text(symptom)}. Routed to: {', '.join(routed_skills)}.",
        refreshed_at=refreshed_at, scope_summary=scope_summary, partial=partial,
        warnings=warnings, scope_coverage=scope_coverage)
    return model
