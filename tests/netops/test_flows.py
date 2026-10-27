"""netops-flow-insights engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json

import pytest

from conftest import SKILLS, load_json, load_skill_module

flows = load_skill_module("netops-flow-insights", "flows.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

EX = SKILLS / "netops-flow-insights" / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
NET = "/providers/Microsoft.Network"
HUB = SUB + "/resourceGroups/rg-netops-hub" + NET + "/virtualNetworks/vnet-hub"
SPK = SUB + "/resourceGroups/rg-netops-spoke" + NET + "/virtualNetworks/vnet-spoke1"
NSG = SUB + "/resourceGroups/rg-netops-spoke" + NET + "/networkSecurityGroups/nsg-spoke1-app"
NW = SUB + "/resourceGroups/NetworkWatcherRG" + NET + "/networkWatchers/NetworkWatcher_eastus/flowLogs/"
WS = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.OperationalInsights/workspaces/law-netops"

# Every az command listed in SKILL.md "Steps" (placeholders filled with example values).
STEPS_COMMANDS = (
    "az network vnet list -o json",
    "az network watcher flow-log list --location eastus -o json",
    "az network watcher flow-log show --location eastus --name fl-vnet-hub -o json",
)


def flow_log(name, target, enabled=True, ta=True):
    return {"id": NW + name, "name": name, "location": "eastus", "targetResourceId": target,
            "enabled": enabled, "retentionPolicy": {"days": 30, "enabled": True},
            "flowAnalyticsConfiguration": {"networkWatcherFlowAnalyticsConfiguration": {
                "enabled": ta, "workspaceResourceId": WS if ta else None, "trafficAnalyticsInterval": 10}}}


def vnet(vid):
    return {"id": vid, "name": vid.rsplit("/", 1)[-1], "location": "eastus"}


def row(dest="10.1.1.4", port=1433, denied=0, allowed=0, ftype="InterVNet", src="10.0.1.4", target=HUB, **extra):
    r = {"TargetResourceId": target, "FlowType": ftype, "SrcIp": src, "DestIp": dest, "DestPort": port,
         "L4Protocol": "T", "AclGroup": "", "AclRule": "DenyAllInBound", "AllowedInFlows": allowed,
         "AllowedOutFlows": 0, "DeniedInFlows": denied, "DeniedOutFlows": 0,
         "BytesSrcToDest": 0, "BytesDestToSrc": 0}
    r.update(extra)
    return r


def healthy():
    return {
        "managed_scopes": [SUB],
        "vnets": [vnet(HUB)],
        "flow_logs": [flow_log("fl-vnet-hub", HUB)],
        "flow_rows": [row(allowed=50, BytesSrcToDest=1000, BytesDestToSrc=2000)],
    }


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings_and_full_coverage():
    r = flows.analyze(healthy())
    assert r["skill"] == "netops-flow-insights"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"flow_log_coverage_pct": 100.0}
    assert any(m["label"] == "Top talker #1" and m["value"] == "10.0.1.4 -> 10.1.1.4" for m in r["metrics"])


def test_example_output_is_deterministic():
    data = load_json(EX / "flowlog-coverage-input.json")
    expected = load_json(EX / "flowlog-coverage-output.json")
    assert flows.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(flows.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_example_covers_every_finding_type():
    r = flows.analyze(load_json(EX / "flowlog-coverage-input.json"))
    for prefix in ("FLOW-VNET-NO-FLOWLOG:", "FLOW-LOG-DISABLED:", "FLOW-TA-DISABLED:",
                   "FLOW-NSG-FLOWLOG-RETIRING:", "FLOW-DENIED-HIGH:", "FLOW-MALICIOUS:"):
        assert by_prefix(r, prefix), prefix
    assert r["kpis"]["flow_log_coverage_pct"] == 33.3
    assert r["findings"][0]["severity"] == "high"


def test_vnet_without_flow_log_lowers_coverage():
    d = healthy()
    d["vnets"].append(vnet(SPK))
    d["flow_logs"].append(flow_log("fl-snet", SPK + "/subnets/snet-app"))
    r = flows.analyze(d)
    f = by_prefix(r, "FLOW-VNET-NO-FLOWLOG:")
    assert [x["severity"] for x in f] == ["medium"]
    assert f[0]["evidence"]["subnet_flow_logs"] == ["snet-app"]
    assert r["kpis"]["flow_log_coverage_pct"] == 50.0


def test_disabled_flow_log_is_medium_and_not_double_reported():
    d = healthy()
    d["flow_logs"] = [flow_log("fl-vnet-hub", HUB, enabled=False)]
    r = flows.analyze(d)
    assert [x["severity"] for x in by_prefix(r, "FLOW-LOG-DISABLED:")] == ["medium"]
    assert by_prefix(r, "FLOW-VNET-NO-FLOWLOG:") == []
    assert by_prefix(r, "FLOW-TA-DISABLED:") == []
    assert r["kpis"]["flow_log_coverage_pct"] == 0.0


def test_traffic_analytics_disabled_is_low():
    d = healthy()
    d["flow_logs"] = [flow_log("fl-vnet-hub", HUB, ta=False)]
    assert [x["severity"] for x in by_prefix(flows.analyze(d), "FLOW-TA-DISABLED:")] == ["low"]


def test_arm_properties_shape_is_accepted():
    d = healthy()
    fl = flow_log("fl-vnet-hub", HUB, ta=False)
    d["flow_logs"] = [{"id": fl["id"], "name": fl["name"], "location": "eastus",
                       "properties": {k: v for k, v in fl.items() if k not in ("id", "name", "location")}}]
    r = flows.analyze(d)
    assert r["kpis"]["flow_log_coverage_pct"] == 100.0
    assert by_prefix(r, "FLOW-TA-DISABLED:")


@pytest.mark.parametrize("enabled,severity", [(True, "medium"), (False, "low")])
def test_nsg_flow_log_retirement(enabled, severity):
    d = healthy()
    d["flow_logs"].append(flow_log("fl-nsg", NSG, enabled=enabled))
    f = by_prefix(flows.analyze(d), "FLOW-NSG-FLOWLOG-RETIRING:")
    assert [x["severity"] for x in f] == [severity]
    assert f[0]["evidence"]["retirement_date"] == "2027-09-30"


def test_high_denied_flows_to_destination():
    d = healthy()
    d["flow_rows"] = [row(denied=70, src="10.0.1.4"), row(denied=40, src="10.0.1.5"), row(dest="10.1.1.5", denied=99)]
    f = by_prefix(flows.analyze(d), "FLOW-DENIED-HIGH:")
    assert [x["id"] for x in f] == ["FLOW-DENIED-HIGH:10.1.1.4:1433/T"]
    assert f[0]["severity"] == "medium" and "SC-04" in f[0]["recommendation"]
    assert f[0]["evidence"]["acl_rules"] == ["DenyAllInBound"]
    d["thresholds"] = {"denied_flows": 500}
    assert by_prefix(flows.analyze(d), "FLOW-DENIED-HIGH:") == []


def test_malicious_flows_are_high_with_threat_details():
    d = healthy()
    d["flow_rows"].append({"Query": "malicious", "TargetResourceId": HUB, "FlowType": "MaliciousFlow",
                           "PublicIp": "203.0.113.50", "FlowDirection": "I", "DestPort": 22,
                           "AllowedInFlows": 2, "DeniedInFlows": 5})
    d["ip_details"] = [{"Ip": "203.0.113.50", "FlowType": "MaliciousFlow", "ThreatType": "Botnet"}]
    f = by_prefix(flows.analyze(d), "FLOW-MALICIOUS:")
    assert [x["severity"] for x in f] == ["high"]
    assert f[0]["evidence"]["threat"]["ThreatType"] == "Botnet"
    d["flow_rows"] = [row(ftype="MaliciousFlow", src="", dest="",
                          SrcPublicIps="198.51.100.7|1|2|3|4|5|6", allowed=1)]
    assert [x["id"] for x in by_prefix(flows.analyze(d), "FLOW-MALICIOUS:")] == ["FLOW-MALICIOUS:198.51.100.7"]


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = flows.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) == 3
    assert any("Traffic Analytics data not queried" in g for g in r["evidence_gaps"])
    assert r["kpis"] == {}
    d = healthy()
    d["flow_rows"] = []
    assert flows.analyze(d)["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    foreign = OTHER + "/resourceGroups/x" + NET + "/virtualNetworks/vnet-x"
    d["vnets"].append(vnet(foreign))
    d["flow_rows"].append(row(target=foreign, denied=1000))
    r = flows.analyze(d)
    assert r["findings"] == [] and r["kpis"]["flow_log_coverage_pct"] == 100.0
    assert "1 vnets item(s) outside the managed scope were excluded." in r["warnings"]
    assert "1 flow_rows item(s) outside the managed scope were excluded." in r["warnings"]
    d["managed_scopes"] = None
    r = flows.analyze(d)
    assert by_prefix(r, "FLOW-VNET-NO-FLOWLOG:") and by_prefix(r, "FLOW-DENIED-HIGH:")


def test_rows_without_arm_target_are_kept_with_warning():
    d = healthy()
    d["flow_rows"] = [row(target="", denied=500)]
    r = flows.analyze(d)
    assert by_prefix(r, "FLOW-DENIED-HIGH:")
    assert any("could not be scope-checked" in w for w in r["warnings"])


def test_remediation_scripts_are_human_review_and_commented():
    r = flows.analyze(load_json(EX / "flowlog-coverage-input.json"))
    for f in r["findings"]:
        lines = f["remediation_script"].splitlines()
        assert lines[0] == "# Human review required. Read-only verification (the agent never runs writes):"
        for line in lines[1:]:
            if line.startswith("az "):
                assert guard.classify_az_command(line)["decision"] in ("allow_read", "allow_diagnostic"), line
            else:
                assert line.startswith("#") or line.startswith("NTA"), line
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        flows.analyze([])
    with pytest.raises(ValueError):
        flows.analyze({"flow_logs": {}})
    with pytest.raises(ValueError):
        flows.analyze({"ip_details": "x"})


def test_result_renders_through_adapter():
    r = flows.analyze(load_json(EX / "flowlog-coverage-input.json"))
    model = models.build_flow_insights_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "FLOW-VNET-NO-FLOWLOG" in html
    with pytest.raises(ValueError):
        models.build_ip_capacity_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert flows.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-flow-insights"


@pytest.mark.parametrize("command", STEPS_COMMANDS)
def test_skill_steps_commands_are_read_only(command):
    assert guard.classify_az_command(command)["decision"] in ("allow_read", "allow_diagnostic")
