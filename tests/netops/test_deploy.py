"""Deploy (Bicep + deploy.sh) and installer (install-api.sh) checks for the NetOps plugin.

Mirrors dmauser/finops-sre-agent-pack tests/test_deploy.py and the installer-heredoc checks in
tests/test_agent_manifest.py, adapted to the NetOps least-privilege, read-only RBAC model.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NETOPS = ROOT / "plugins" / "netops"
DEPLOY = NETOPS / "deploy"
INSTALLER = NETOPS / "install-api.sh"
TASK_RENDERER = NETOPS / "scheduled-tasks" / "render_tasks.py"
AGENT_MANIFEST = NETOPS / "agents" / "netops-investigator.json"
GUARD = NETOPS / "skills" / "netops-managed-scope" / "readonly_guard.py"
AGENT_ID = "/subscriptions/s/resourceGroups/r/providers/Microsoft.App/agents/a"

ALL_SKILLS = {
    "netops-managed-scope",
    "netops-report-renderer",
    "netops-hybrid-health",
    "netops-private-endpoint-dns",
    "netops-routing-analyzer",
    "netops-nsg-firewall-audit",
    "netops-exposure-scan",
    "netops-snat-egress",
    "netops-ip-capacity",
    "netops-flow-insights",
}

# Built-in role IDs, https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
MONITORING_READER = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
LOG_ANALYTICS_READER = "73c42c96-874c-492b-b04d-ab87d138a893"
FORBIDDEN_ROLES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "4d97b98b-1d4f-4787-a291-c67834d212e7": "Network Contributor",
    "749f88d5-cbae-40b8-bcfc-e573ddc772fa": "Monitoring Contributor",
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(path):
    return path.read_text(encoding="utf-8")


# ---- Bicep ---------------------------------------------------------------------------------

def test_bicep_grants_only_read_only_roles():
    main = _text(DEPLOY / "main.bicep")
    agent = _text(DEPLOY / "agent.bicep")
    for role in (READER, MONITORING_READER, LOG_ANALYTICS_READER):
        assert role in main
    assert "e79298df-d852-4c6d-84f9-5d13249d1e55" in agent  # SRE Agent Administrator (deployer)
    assert "Microsoft.App/agents@" in agent
    for role_id, role_name in FORBIDDEN_ROLES.items():
        assert role_id not in main + agent, f"{role_name} must never be granted"


def test_custom_diagnostics_role_matches_readonly_guard():
    guard = _load(GUARD, "netops_guard_deploy")
    main = _text(DEPLOY / "main.bicep")
    block = re.search(r"var diagnosticActions = \[(.*?)\]", main, re.S).group(1)
    actions = re.findall(r"'([^']+)'", block)
    assert sorted(actions) == sorted(guard.custom_role_actions())
    for action in actions:
        assert action.endswith("/action")
        assert guard.classify_arm_action(action) != "write"
    assert "type: 'customRole'" in main
    assert "NetOps Network Diagnostics Reader" in main
    assert "notActions: []" in main
    assert "/write" not in block and "/delete" not in block and "*" not in block


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_deploy_scripts_parse():
    for path in (DEPLOY / "deploy.sh", INSTALLER):
        # stdin avoids Windows-path mangling when `bash` resolves to WSL.
        subprocess.run(["bash", "-n"], input=path.read_bytes(), check=True)


def test_deploy_script_defaults_and_handoff():
    script = _text(DEPLOY / "deploy.sh")
    assert 'DEFAULT_AGENT_NAME="sre-netops-demo"' in script
    assert 'DEFAULT_RESOURCE_GROUP="SRE-NetOps-Demo"' in script
    assert 'DEFAULT_TASK_IDS="all"' in script
    assert "env -u AGENT_NAME" in script
    assert 'PLUGIN_SOURCE="${PLUGIN_SOURCE:-direct}"' in script
    assert len(re.findall(r'^ask [A-Z_]+ "', script, re.MULTILINE)) == 3
    assert "finops" not in script.lower().replace("finops-sre-agent-pack", "")


# ---- install-api.sh ------------------------------------------------------------------------

def test_installer_core_contract():
    script = _text(INSTALLER)
    assert 'PLUGIN_NAME="${PLUGIN_NAME:-netops}"' in script
    assert 'PLUGIN_PATH="${PLUGIN_PATH:-plugins/netops}"' in script
    assert 'REPO_SLUG="${REPO_SLUG:-dmauser/network-desk}"' in script
    assert 'PLUGIN_SOURCE="${PLUGIN_SOURCE:-marketplace}"' in script
    assert "/api/v2/plugins/install-direct" in script
    assert 'TASK_IDS="${TASK_IDS:-all}"' in script
    assert "render_tasks.py" in script or "TASK_RENDERER" in script
    for skill in ALL_SKILLS:
        assert f'"{skill}"' in script
    assert "Network Contributor" in script  # documented as NOT required
    for role in ('"Reader"', '"Monitoring Reader"', '"Log Analytics Reader"'):
        assert role in script
    assert "Cost Management" not in script
    assert "Monitoring Contributor" not in script


def test_installer_never_executes_network_writes():
    script = _text(INSTALLER)
    # The only az write verbs allowed are RBAC grants for the read-only roles.
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not re.search(r"\baz\s+network\b", stripped):
            continue
        assert not re.search(r"\b(create|update|delete|set|add|remove|reset)\b", stripped), stripped


def _agent_heredoc():
    script = _text(INSTALLER)
    match = re.search(r"python3 - \"\$agent_body\" <<'PY'\n(.*?)\nPY\n", script, re.S)
    assert match, "agent body heredoc not found"
    return match.group(1)


def _run_heredoc(tmp_path, **env_overrides):
    code = tmp_path / "agent_body.py"
    code.write_text(_agent_heredoc(), encoding="utf-8")
    out = tmp_path / "body.json"
    env = dict(os.environ)
    env.update(
        NETOPS_AGENT_NAME="netops-investigator",
        NETOPS_AGENT_MANIFEST=str(AGENT_MANIFEST),
        NETOPS_MCP_TOOLS="",
        NETOPS_CONNECTORS="",
        NETOPS_KUSTO_TOOL="",
        NETOPS_PYTHON_TOOL="ExecutePythonCode",
        AGENT_RESOURCE_ID=AGENT_ID,
    )
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, str(code), str(out)], env=env, capture_output=True, text=True
    )
    return proc, out


def test_installer_agent_body_injects_scope_and_keeps_tools_read_only(tmp_path):
    proc, out = _run_heredoc(tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    doc = json.loads(out.read_text(encoding="utf-8"))
    props = doc["properties"]
    assert props["tools"] == [
        "RunAzCliReadCommands",
        "ExecutePythonCode",
        "ListReports",
        "GetReport",
        "SaveReport",
    ]
    assert AGENT_ID in props["instructions"]
    for placeholder in ("__AGENT_RESOURCE_ID__", "{{AGENT_RESOURCE_ID}}", "${AGENT_RESOURCE_ID}"):
        assert placeholder not in props["instructions"]
    assert ALL_SKILLS <= set(props["allowedSkills"])


def test_installer_agent_body_optional_kusto_tool_and_terminal(tmp_path):
    proc, out = _run_heredoc(
        tmp_path, NETOPS_KUSTO_TOOL="netops-kql", NETOPS_PYTHON_TOOL="RunInTerminal",
        NETOPS_MCP_TOOLS="a, b", NETOPS_CONNECTORS="c",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    props = json.loads(out.read_text(encoding="utf-8"))["properties"]
    assert props["tools"][-1] == "netops-kql"
    assert "RunInTerminal" in props["tools"] and "ExecutePythonCode" not in props["tools"]
    assert {"a", "b"} <= set(props["mcpTools"])
    assert "c" in props["connectors"]


def test_installer_agent_body_rejects_unknown_python_tool(tmp_path):
    proc, _ = _run_heredoc(tmp_path, NETOPS_PYTHON_TOOL="RunAzCliWriteCommands")
    assert proc.returncode != 0


def test_installer_agent_body_rejects_tampered_manifest(tmp_path):
    doc = json.loads(AGENT_MANIFEST.read_text(encoding="utf-8"))
    doc["properties"]["tools"].append("RunAzCliWriteCommands")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc, _ = _run_heredoc(tmp_path, NETOPS_AGENT_MANIFEST=str(bad))
    assert proc.returncode != 0
    assert "read-only" in (proc.stdout + proc.stderr).lower()


def test_task_selection(monkeypatch):
    module = _load(TASK_RENDERER, "netops_task_renderer_deploy")
    monkeypatch.setenv("AGENT_RESOURCE_ID", AGENT_ID)
    monkeypatch.setenv("TASK_AGENT_NAME", "netops-investigator")
    tasks = module.load_manifest()
    assert module.select_tasks(tasks, "all") == tasks
    chosen = module.select_tasks(tasks, " hybrid-health , kpi-scorecard ")
    assert {t["id"] for t in chosen} == {"hybrid-health", "kpi-scorecard"}
    with pytest.raises(ValueError, match="Unknown TASK_IDS: nope"):
        module.select_tasks(tasks, "hybrid-health,nope")


def test_plugin_manifest_and_marketplace():
    plugin = json.loads(_text(NETOPS / "plugin.json"))
    assert plugin["name"] == "netops"
    assert plugin["license"] == "MIT"
    assert plugin["skills"] == ["skills/"]
    skill_dirs = {p.name for p in (NETOPS / "skills").iterdir() if (p / "SKILL.md").exists()}
    assert skill_dirs == ALL_SKILLS
    market = json.loads(_text(ROOT / ".github" / "plugin" / "marketplace.json"))
    entry = next(p for p in market["plugins"] if p["name"] == "netops")
    assert entry["source"] == "./plugins/netops"
    assert entry["version"] == plugin["version"]
