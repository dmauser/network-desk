"""NetOps scheduled tasks: manifest, generated YAML, managed-scope preamble, rendering and install plan."""

import importlib.util
import json
import re
import sys

import pytest
import yaml

from conftest import PLUGIN, SKILLS

TASKS = PLUGIN / "scheduled-tasks"
_spec = importlib.util.spec_from_file_location("netops_render_tasks", TASKS / "render_tasks.py")
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

AGENT_ID = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.App/agents/sre1"
CADENCE = {
    "hybrid-health": "daily",
    "nsg-firewall-audit": "weekly",
    "pe-dns-validation": "weekly",
    "exposure-scan": "weekly",
    "capacity-forecast": "monthly",
    "kpi-scorecard": "monthly",
}


def _cadence(cron):
    minute, hour, dom, month, dow = cron.split()
    if dom == "*" and dow == "*":
        return "daily"
    if dom == "*" and dow != "*":
        return "weekly"
    if dom != "*" and dow == "*":
        return "monthly"
    return "other"


@pytest.fixture
def install_env(monkeypatch):
    monkeypatch.setenv("AGENT_RESOURCE_ID", AGENT_ID)
    monkeypatch.setenv("TASK_AGENT_NAME", "sre1")
    for var in ("ALERT_EMAIL", "TASK_IDS", "MODEL_TIER"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_generated_yaml_is_current():
    assert rt.write_or_check(True) == 0


def test_manifest_ids_cadence_and_unique_names():
    tasks = rt.load_manifest()
    assert {t["id"]: _cadence(t["defaultCron"]) for t in tasks} == CADENCE
    for key in ("defaultName", "defaultReportName", "nameEnv", "cronEnv", "modelEnv", "reportNameEnv", "yaml"):
        values = [t[key] for t in tasks]
        assert len(values) == len(set(values)), key
    for t in tasks:
        assert t["defaultName"].startswith("NetOps: ")
        assert t["defaultReportName"].startswith("NetOps: ")
        assert "netops" in t["tags"] and "netops-live-report" in t["tags"]


@pytest.mark.parametrize("task", rt.load_manifest(), ids=lambda t: t["id"])
def test_yaml_reference_has_strict_preamble_and_read_only_contract(task):
    text = (TASKS / task["yaml"]).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    assert doc["apiVersion"] == "azuresre.ai/v1" and doc["kind"] == "ScheduledTask"
    assert doc["metadata"]["name"] == doc["spec"]["name"] == task["defaultName"]
    assert doc["spec"]["agent"] == "__AGENT_NAME__"
    assert doc["spec"]["cron"] == f"__{task['cronEnv']}__"
    prompt = doc["spec"]["agentPrompt"]
    assert prompt.startswith("STRICT MANAGED-SCOPE PREAMBLE")
    for phrase in (
        "`netops-managed-scope`",
        "`__AGENT_RESOURCE_ID__`",
        "scheduled mode",
        "This task accepts no override",
        "Broad RBAC or visibility must never expand the boundary",
        "FAIL CLOSED",
        "netscope.filter_resources",
        "readonly_guard.assert_read_only",
        "never execute a remediation script",
        "allowedTools: []",
        "never execute it",
        "`__ALERT_EMAIL__`",
    ):
        assert phrase in prompt, phrase
    assert prompt.index("FAIL CLOSED") < prompt.index("SaveReport the generated")
    assert "{{" not in prompt and "}}" not in prompt


@pytest.mark.parametrize("task", rt.load_manifest(), ids=lambda t: t["id"])
def test_prompt_references_real_skills_engines_and_adapters(task):
    sys.path.insert(0, str(SKILLS / "netops-report-renderer"))
    try:
        import models
        import scorecard
    finally:
        sys.path.pop(0)
    prompt = (TASKS / task["prompt"]).read_text(encoding="utf-8")
    skills = set(re.findall(r"`(netops-[a-z-]+)`", prompt))
    assert skills, task["id"]
    for skill in skills:
        assert (SKILLS / skill / "SKILL.md").is_file(), skill
    engines = set(re.findall(r"`([a-z]+\.py)`", prompt)) - {"models.py", "render.py", "scorecard.py"}
    on_disk = {p.name for s in skills for p in (SKILLS / s).glob("*.py")}
    assert engines and engines <= on_disk, engines - on_disk
    for adapter in re.findall(r"`(build_[a-z_]+)\(", prompt):
        assert hasattr(models, adapter) or hasattr(scorecard, adapter), adapter


def test_api_payloads_substitute_install_values(install_env):
    payloads = rt.render_api_payloads()
    assert len(payloads) == 6
    for p in payloads:
        assert set(p) == {"name", "description", "cronExpression", "agentPrompt", "agent", "agentMode", "modelTier"}
        assert p["agent"] == "sre1" and AGENT_ID in p["agentPrompt"]
        assert "__" not in re.sub(r"`[^`]*\.py`|__init__", "", p["agentPrompt"])
        assert "{{" not in p["agentPrompt"]
        assert "ALERT_EMAIL was not set" in p["agentPrompt"]


def test_alert_email_and_overrides(install_env):
    install_env.setenv("ALERT_EMAIL", "netops@contoso.com")
    install_env.setenv("HYBRID_CRON", "15 5 * * *")
    install_env.setenv("HYBRID_REPORT_NAME", "Hub Hybrid Health")
    install_env.setenv("TASK_IDS", "hybrid-health")
    [payload] = rt.render_api_payloads()
    assert payload["cronExpression"] == "15 5 * * *"
    assert "email `netops@contoso.com` with subject `NetOps hybrid connectivity alert" in payload["agentPrompt"]
    assert "`Hub Hybrid Health`" in payload["agentPrompt"]


def test_unknown_task_ids_and_control_chars_rejected(install_env):
    install_env.setenv("TASK_IDS", "nope")
    with pytest.raises(ValueError, match="Unknown TASK_IDS"):
        rt.render_api_payloads()
    install_env.setenv("TASK_IDS", "all")
    install_env.setenv("HYBRID_TASK_NAME", "bad\nname")
    with pytest.raises(ValueError, match="control characters"):
        rt.render_api_payloads()


def test_install_plan_and_verify(install_env, tmp_path):
    existing = tmp_path / "existing.json"
    existing.write_text(json.dumps({"value": [
        {"id": "t-1", "name": "NetOps: Exposure Scan (Weekly)", "agent": "sre1", "status": "Active"},
    ]}), encoding="utf-8")
    out = tmp_path / "plan"
    rt.write_install_plan(existing, out)
    rows = (out / "task-plan.tsv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 6 and (out / "task-count.txt").read_text().strip() == "6"
    exposure = next(r.split("\x1f") for r in rows if "Exposure" in r)
    assert exposure[4] == "t-1"
    assert len((out / "reports.txt").read_text(encoding="utf-8").strip().splitlines()) == 6
    expected = out / "expected-tasks.json"
    assert rt.verify_install(existing, expected) == 1
    names = [t["name"] for t in json.loads(expected.read_text(encoding="utf-8"))["tasks"]]
    existing.write_text(json.dumps([{"id": f"i{n}", "name": name, "agent": "sre1"} for n, name in enumerate(names)]), encoding="utf-8")
    assert rt.verify_install(existing, expected) == 0


def test_prompts_contain_no_write_commands():
    for path in (TASKS / "prompts").glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\baz\s+[a-z -]+\s(create|delete|update|set|reset)\b", text), path.name
