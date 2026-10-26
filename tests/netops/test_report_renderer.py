"""netops-report-renderer: models, scorecard and the FinOps-derived renderer."""

import copy

import pytest

from conftest import SKILLS, load_json, load_skill_module

models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
scorecard = load_skill_module("netops-report-renderer", "scorecard.py")
EXAMPLE = SKILLS / "netops-report-renderer" / "examples" / "hybrid-result.json"
NOW = "2026-10-26T06:00:00Z"


def _finding(**overrides):
    base = {"id": "X-1", "skill": "netops-exposure-scan", "severity": "high",
            "resource_id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/publicIPAddresses/p",
            "title": "t", "evidence": "e", "recommendation": "r"}
    base.update(overrides)
    return base


def test_every_skill_has_an_adapter_with_matching_title():
    assert set(models.ADAPTERS) == set(models.SKILL_REPORTS)
    for skill, adapter in models.ADAPTERS.items():
        model = adapter({"findings": []}, refreshed_at=NOW)
        assert model["title"] == models.SKILL_REPORTS[skill][0]
        assert models.DISCLAIMER in model["description"]
        render.render_report(model)


def test_example_renders_deterministically_and_escapes():
    result = load_json(EXAMPLE)
    result["findings"][0]["title"] = "<script>alert(1)</script>"
    before = copy.deepcopy(result)
    model = models.build_hybrid_health_model(result, refreshed_at=NOW, scope_summary=["/subscriptions/s"])
    assert result == before, "adapter must not mutate input"
    html_a = render.render_report(model)
    html_b = render.render_report(models.build_hybrid_health_model(result, refreshed_at=NOW,
                                                                   scope_summary=["/subscriptions/s"]))
    assert html_a == html_b
    assert "<script>alert(1)</script>" not in html_a
    assert "netops-chart" in html_a and "finops" not in html_a
    assert "Remediation scripts (human review required)" in html_a


def test_findings_sorted_by_severity_then_skill_resource_id():
    result = {"findings": [_finding(id="b", severity="low"), _finding(id="a", severity="critical"),
                           _finding(id="c", severity="critical", resource_id="")]}
    model = models.build_findings_model(result, title="t", description="d", refreshed_at=NOW)
    rows = model["sections"][0]["rows"]
    assert [r[0] for r in rows] == ["CRITICAL", "CRITICAL", "LOW"]
    assert rows[0][2] == "(scope)"


def test_evidence_gaps_force_partial_and_warning():
    model = models.build_exposure_scan_model({"findings": [], "evidence_gaps": ["no ARG access"]},
                                             refreshed_at=NOW)
    assert model["partial"] is True
    assert "Evidence gap: no ARG access" in model["warnings"]


@pytest.mark.parametrize("bad", [
    {"severity": "urgent"}, {"id": ""}, {"title": ""}, {"citations": "x"},
])
def test_invalid_findings_rejected(bad):
    with pytest.raises(ValueError):
        models.build_findings_model({"findings": [_finding(**bad)]}, title="t", description="d",
                                    refreshed_at=NOW)


def test_duplicate_ids_rejected_and_refreshed_at_required():
    with pytest.raises(ValueError):
        models.build_findings_model({"findings": [_finding(), _finding()]}, title="t",
                                    description="d", refreshed_at=NOW)
    with pytest.raises(ValueError):
        models.build_findings_model({"findings": []}, title="t", description="d", refreshed_at="")


def test_adapter_rejects_result_for_another_skill():
    with pytest.raises(ValueError):
        models.build_hybrid_health_model({"skill": "netops-ip-capacity", "findings": []}, refreshed_at=NOW)


def test_scope_coverage_rows_validated():
    model = models.build_ip_capacity_model(
        {"findings": []}, refreshed_at=NOW,
        scope_coverage=[{"scope": "/subscriptions/s", "status": "partial", "included_count": 3,
                         "excluded_count": 1, "unattributed_count": 0, "partial": True}])
    assert model["partial"] is True
    assert model["sections"][3]["rows"] == [["/subscriptions/s", "partial", "3", "1", "0", ""]]
    with pytest.raises(ValueError):
        models.build_ip_capacity_model({"findings": []}, refreshed_at=NOW,
                                       scope_coverage=[{"scope": "s", "included": "3"}])


def test_triage_model_merges_skills():
    model = models.build_triage_model(
        [{"skill": "netops-routing-analyzer", "findings": [_finding(id="r1", skill=None)]},
         {"skill": "netops-hybrid-health", "findings": [], "evidence_gaps": ["bgp"]}],
        symptom="on-prem cannot reach spoke", routed_skills=["netops-routing-analyzer", "netops-hybrid-health"],
        refreshed_at=NOW)
    assert model["sections"][0]["rows"][0][1] == "netops-routing-analyzer"
    assert model["partial"] is True
    assert "netops-hybrid-health: bgp" in model["sections"][2]["rows"][0][0]


def test_scorecard_grades_and_marks_unknown():
    results = [{"skill": "netops-hybrid-health", "kpis": {"tunnels_connected_pct": 100, "bgp_peers_connected_pct": 95}},
               {"skill": "netops-exposure-scan", "kpis": {"risky_mgmt_exposures": 2}}]
    card = scorecard.compute_scorecard(results)
    status = {r["kpi"]: r["status"] for r in card["rows"]}
    assert status["tunnels_connected_pct"] == "good"
    assert status["bgp_peers_connected_pct"] == "warning"
    assert status["risky_mgmt_exposures"] == "critical"
    assert status["flow_log_coverage_pct"] == "unknown"
    assert card["score"] == 50 and card["graded"] == 3
    model = scorecard.build_scorecard_model(results, refreshed_at=NOW)
    assert model["partial"] is True
    assert model["sections"][0]["title"] == "KPI scorecard"
    render.render_report(model)


def test_scorecard_kpis_reference_known_skills():
    for key, _label, skill, _unit, direction, good, warning in scorecard.KPI_DEFINITIONS:
        assert skill in models.SKILL_REPORTS, key
        assert direction in {"min", "max"}
        assert (good >= warning) if direction == "min" else (good <= warning)


@pytest.mark.parametrize("value", ["90", True, [1]])
def test_scorecard_rejects_non_numeric_kpis(value):
    with pytest.raises(ValueError):
        scorecard.compute_scorecard([{"skill": "netops-ip-capacity", "kpis": {"subnets_over_threshold": value}}])
