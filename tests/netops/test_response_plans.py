"""Incident response plan specs: schema, semantics, and printed portal / azmcp forms."""

import copy
import importlib.util

import pytest

from conftest import PLUGIN

PLANS_DIR = PLUGIN / "response-plans"
_spec = importlib.util.spec_from_file_location("netops_validate_plans", PLANS_DIR / "validate_plans.py")
vp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vp)

EXPECTED = {
    "netops-hybrid-connectivity-down": "netops-hybrid-health",
    "netops-paas-unreachable-private-endpoint": "netops-private-endpoint-dns",
    "netops-latency-drops-snat": "netops-snat-egress",
    "netops-asymmetric-routing-nva": "netops-routing-analyzer",
}


def _plans():
    return {plan["metadata"]["name"]: plan for _, plan in vp.load_plans()}


def _schema():
    import json

    return json.loads(vp.SCHEMA.read_text(encoding="utf-8"))


def test_check_passes(capsys):
    assert vp.main(["check"]) == 0
    assert "4 plan(s) checked, 0 with errors" in capsys.readouterr().out


def test_four_plans_route_to_expected_skills_in_review_mode():
    plans = _plans()
    assert {n: p["investigation"]["primarySkill"] for n, p in plans.items()} == EXPECTED
    for plan in plans.values():
        assert plan["handler"]["customAgent"] == "netops-investigator"
        assert plan["handler"]["autonomy"] == "Review"
        assert plan["azureMcp"]["agentMode"] == "review"
        assert plan["remediation"]["mode"] == "human-review-only"


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda p: p["handler"].__setitem__("autonomy", "Autonomous"), "not in ['Review']"),
        (lambda p: p["filter"].__setitem__("severities", ["P1"]), "not in ['Sev0'"),
        (lambda p: p["handler"]["reinvestigationCooldown"].__setitem__("hours", 48), "above maximum"),
        (lambda p: p.__setitem__("extra", 1), "unexpected property 'extra'"),
        (lambda p: p.pop("citations"), "missing required 'citations'"),
        (lambda p: p["citations"].append("https://example.com/x"), "does not match"),
    ],
)
def test_schema_rejects_invalid(mutate, needle):
    plan = copy.deepcopy(next(iter(_plans().values())))
    mutate(plan)
    assert any(needle in e for e in vp.validate_schema(plan, _schema()))


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda p: p["investigation"].__setitem__("primarySkill", "netops-nope"), "unknown skill"),
        (lambda p: p["investigation"]["steps"].insert(0, "Run netops-hybrid-health first."), "managed scope"),
        (lambda p: p["investigation"]["steps"].append("Fix it with az network vpn-connection reset --yes"), "write operation"),
        (lambda p: p["investigation"]["steps"].append("a; b"), "separator"),
        (lambda p: p["alertSignals"].append({"resourceType": "Microsoft.Network/natGateways", "metric": "MadeUp", "hint": "x"}), "unverified metric"),
        (lambda p: p.__setitem__("investigation", {**p["investigation"], "steps": [s for s in p["investigation"]["steps"] if "renderer" not in s]}), "netops-report-renderer"),
    ],
)
def test_semantics_reject_invalid(mutate, needle):
    plan = copy.deepcopy(_plans()["netops-hybrid-connectivity-down"])
    mutate(plan)
    assert any(needle in e for e in vp.semantic_errors(plan, vp._routing_skills()))


def test_portal_and_azmcp_output(capsys):
    vp.main(["portal"])
    out = capsys.readouterr().out
    assert out.count("Agent autonomy level        : Review") == 4
    assert "Title contains              : netops-hybrid" in out
    vp.main(["azmcp", "--agent", "sre1", "--resource-group", "rg1"])
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("azmcp ")]
    assert len(lines) == 4
    for line in lines:
        assert "--agent sre1" in line and "--agent-mode review" in line and "--resource-group rg1" in line
