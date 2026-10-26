"""Pytest wrapper for the NetOps eval scenarios (also validates fixture shape and the router)."""

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("netops_eval_run", HERE / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

FIXTURES = run.fixture_paths()


def test_fixtures_exist():
    assert len(FIXTURES) >= 4


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_scenario(path):
    fixture = run.load_fixture(path)
    assert fixture["expected_skill"] in run.ENGINES
    assert fixture["source"].startswith("https://github.com/dmauser/")
    result = run.evaluate(fixture)
    assert result["passed"], result["failures"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_followup_skills_are_known(path):
    routing = run.load_routing()
    known = {s["skill"] for s in routing["skills"]} | {routing["fallbackSkill"]}
    for skill in run.load_fixture(path).get("followup_skills", []):
        assert skill in known, skill


def test_router_fallback_and_ties():
    assert run.route("something completely unrelated")[0] == ("netops-routing-analyzer", 0)
    assert run.route("BGP over the site-to-site VPN is flapping")[0][0] == "netops-hybrid-health"
    assert run.route("private endpoint resolves to a public IP")[0][0] == "netops-private-endpoint-dns"


def test_runner_reports_failures(tmp_path):
    fixture = run.load_fixture(FIXTURES[0])
    fixture["expected_skill"] = "netops-private-endpoint-dns"
    fixture["input"] = {}
    fixture["expect"] = {"finding_prefixes": ["NOPE-"], "partial": False}
    result = run.evaluate(fixture)
    assert not result["passed"]
    assert any("routed to" in f for f in result["failures"])
    assert any("NOPE-" in f for f in result["failures"])


def test_fixture_requires_exactly_one_input(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"id":"x","title":"t","source":"s","injected_fault":"f","symptom":"s",'
                 '"expected_skill":"netops-hybrid-health","expect":{}}', encoding="utf-8")
    with pytest.raises(ValueError):
        run.load_fixture(p)


def test_main_exit_code(capsys):
    assert run.main([]) == 0
    assert "scenarios passed" in capsys.readouterr().out
