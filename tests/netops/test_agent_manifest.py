"""netops-investigator manifest, YAML template and routing consistency (mirrors FinOps test_agent_manifest)."""

import importlib.util
import json

import pytest

from conftest import PLUGIN, SKILLS

AGENTS = PLUGIN / "agents"
MANIFEST = AGENTS / "netops-investigator.json"
TEMPLATE = AGENTS / "netops-investigator.yaml"

_spec = importlib.util.spec_from_file_location("netops_render_agent_yaml", AGENTS / "render_agent_yaml.py")
render_agent_yaml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_agent_yaml)

AGENT_ID = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.App/agents/agent"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _routing():
    return json.loads((AGENTS / "routing.json").read_text(encoding="utf-8"))


def test_manifest_defines_read_only_netops_agent():
    manifest = _manifest()
    props = manifest["properties"]
    assert manifest["name"] == "netops-investigator"
    assert manifest["type"] == "ExtendedAgent"
    assert {"netops", "read-only"} <= set(manifest["tags"])
    assert props["enableSkills"] is True and props["addSystemSkills"] is True
    assert props["disableDocumentRetrieval"] is True
    assert props["handoffs"] == []

    text = props["instructions"].lower()
    for phrase in (
        "azure execution surface is strictly read-only",
        "external mcp/connectors have their own scopes",
        "never execute azure post, put, patch, or delete",
        "never execute that script",
        "scheduled tasks are always read-only",
        "never change rbac",
        "human decision",
        "before every netops request",
        "managedresources",
        "{{agent_resource_id}}",
        "scheduled work is strict and fail-closed",
        "explicit confirmation",
        "subsequent turn",
        "broad rbac",
        "evidence gap",
        "analysis only - verify against vendor documentation before applying.",
    ):
        assert phrase in text, phrase


def test_tools_are_read_only_or_report_scoped():
    tools = set(_manifest()["properties"]["tools"])
    assert tools == {"RunAzCliReadCommands", "ExecutePythonCode", "ListReports", "GetReport", "SaveReport"}
    assert not any("write" in t.lower() for t in tools)


def test_allowed_skills_cover_routing_and_exist_on_disk():
    props = _manifest()["properties"]
    allowed = set(props["allowedSkills"])
    routing = _routing()
    routed = {s["skill"] for s in routing["skills"]} | {routing["fallbackSkill"]}
    utility = set(routing["utilitySkills"])
    assert allowed == routed | utility | {"live_report_authoring"}
    for skill in routed | utility:
        assert skill in props["instructions"], skill
        assert (SKILLS / skill).is_dir(), skill
    assert "write_report" in props["instructions"] and "allowedTools empty" in props["instructions"]


def test_yaml_template_is_current_and_substitutes_agent_id():
    assert render_agent_yaml.main(["check"]) == 0
    text = render_agent_yaml.render(AGENT_ID)
    assert text.startswith("# Generated from netops-investigator.json")
    assert "api_version: azuresre.ai/v2" in text and "kind: ExtendedAgent" in text
    assert "  name: netops-investigator" in text
    assert AGENT_ID in text and "{{AGENT_RESOURCE_ID}}" not in text
    assert "{{AGENT_RESOURCE_ID}}" in TEMPLATE.read_text(encoding="utf-8")


def test_render_rejects_non_arm_agent_id():
    with pytest.raises(SystemExit):
        render_agent_yaml.main(["print", "--agent-resource-id", "not-an-id"])
