"""netops-ip-capacity engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json

import pytest

from conftest import SKILLS, load_json, load_skill_module

capacity = load_skill_module("netops-ip-capacity", "capacity.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

EX = SKILLS / "netops-ip-capacity" / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
HUB = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.Network/virtualNetworks/vnet-hub"
SPK = SUB + "/resourceGroups/rg-netops-spoke/providers/Microsoft.Network/virtualNetworks/vnet-spoke1"
ERGW = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.Network/virtualNetworkGateways/ergw-hub"
VPNGW = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.Network/virtualNetworkGateways/vpngw-hub"

# Every az command listed in SKILL.md "Steps" (placeholders filled with example values).
STEPS_COMMANDS = (
    "az network vnet list -o json",
    "az network vnet list -g rg-netops-spoke -o json",
    "az rest --method get --url \"https://management.azure.com" + SPK + "/usages?api-version=2026-01-01\" -o json",
    "az network vnet subnet list -g rg-netops-spoke --vnet-name vnet-spoke1 -o json",
    "az network vnet-gateway list -g rg-netops-hub -o json",
    "az monitor metrics list --resource " + ERGW + " --metric ExpressRouteGatewayCpuUtilization "
    "--aggregation Average --interval PT5M -o json",
    "az monitor metrics list --resource " + VPNGW + " --metric TunnelAverageBandwidth "
    "--aggregation Average --interval PT5M -o json",
)


def subnet(vnet, name, prefix):
    return {"id": f"{vnet}/subnets/{name}", "name": name, "addressPrefix": prefix}


def vnet(vid, space, subnets):
    return {"id": vid, "name": vid.rsplit("/", 1)[-1], "location": "eastus",
            "addressSpace": {"addressPrefixes": space}, "subnets": subnets}


def usage(sid, used, limit):
    return {"id": sid, "currentValue": used, "limit": limit, "name": {"value": "SubnetSpace"}, "unit": "Count"}


def healthy():
    return {
        "managed_scopes": [SUB],
        "as_of": "2025-01-14",
        "vnets": [vnet(SPK, ["10.1.0.0/16"], [subnet(SPK, "snet-app", "10.1.0.0/24")])],
        "usages": [{"vnet_id": SPK, "value": [usage(SPK + "/subnets/snet-app", 40, 251)]}],
        "history": [],
        "gateway_metrics": [],
    }


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings_and_kpi():
    r = capacity.analyze(healthy())
    assert r["skill"] == "netops-ip-capacity"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"subnets_over_threshold": 0}


def test_example_output_is_deterministic():
    data = load_json(EX / "subnet-exhaustion-input.json")
    expected = load_json(EX / "subnet-exhaustion-output.json")
    assert capacity.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(capacity.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_example_covers_every_finding_type():
    r = capacity.analyze(load_json(EX / "subnet-exhaustion-input.json"))
    for prefix in ("CAP-SUBNET-UTIL:", "CAP-SUBNET-FORECAST:", "CAP-SPECIAL-SUBNET-UNDERSIZED:",
                   "CAP-VNET-SPACE-FULL:", "CAP-GW-METRIC:"):
        assert by_prefix(r, prefix), prefix
    assert r["kpis"]["subnets_over_threshold"] == 2
    assert r["findings"][0]["severity"] == "critical"


@pytest.mark.parametrize("used,severity", [(201, "high"), (200, None), (239, "critical"), (250, "critical")])
def test_utilization_severity(used, severity):
    d = healthy()
    d["usages"][0]["value"] = [usage(SPK + "/subnets/snet-app", used, 251)]
    r = capacity.analyze(d)
    f = by_prefix(r, "CAP-SUBNET-UTIL:")
    assert [x["severity"] for x in f] == ([severity] if severity else [])
    assert r["kpis"]["subnets_over_threshold"] == (1 if severity else 0)


def test_thresholds_override_and_unsized_usage_is_skipped():
    d = healthy()
    d["thresholds"] = {"subnet_warn_pct": 10}
    d["usages"][0]["value"].append(usage(SPK + "/subnets/GatewaySubnet", -1, -1))
    r = capacity.analyze(d)
    assert [f["severity"] for f in by_prefix(r, "CAP-SUBNET-UTIL:")] == ["high"]
    assert any("GatewaySubnet" in w for w in r["warnings"])


def test_forecast_projects_exhaustion_date():
    d = healthy()
    d["usages"][0]["value"] = [usage(SPK + "/subnets/snet-app", 150, 251)]
    d["history"] = [{"subnet_id": SPK + "/subnets/snet-app", "as_of": "2024-12-15", "used": 90},
                    {"subnet_id": SPK + "/subnets/snet-app", "as_of": "2024-12-30", "used": 120}]
    f = by_prefix(capacity.analyze(d), "CAP-SUBNET-FORECAST:")
    assert len(f) == 1 and f[0]["severity"] == "medium"
    assert f[0]["evidence"]["growth_ips_per_day"] == 2.0
    assert f[0]["evidence"]["projected_exhaustion"] == "2025-03-06"
    d["thresholds"] = {"forecast_days": 30}
    assert by_prefix(capacity.analyze(d), "CAP-SUBNET-FORECAST:") == []


def test_flat_or_shrinking_history_has_no_forecast():
    d = healthy()
    d["history"] = [{"subnet_id": SPK + "/subnets/snet-app", "as_of": "2024-12-15", "used": 60}]
    assert by_prefix(capacity.analyze(d), "CAP-SUBNET-FORECAST:") == []


def test_history_without_as_of_is_a_gap():
    d = healthy()
    del d["as_of"]
    d["history"] = [{"subnet_id": SPK + "/subnets/snet-app", "as_of": "2024-12-15", "used": 10}]
    r = capacity.analyze(d)
    assert any("as_of missing" in g for g in r["evidence_gaps"]) and r["partial"]


@pytest.mark.parametrize("name,prefix,flagged", [
    ("GatewaySubnet", "10.0.0.0/28", True), ("GatewaySubnet", "10.0.0.0/27", False),
    ("AzureFirewallSubnet", "10.0.0.0/27", True), ("AzureFirewallSubnet", "10.0.0.0/26", False),
    ("AzureBastionSubnet", "10.0.0.0/27", True), ("AzureBastionSubnet", "10.0.0.0/25", False)])
def test_special_subnet_sizing(name, prefix, flagged):
    d = healthy()
    d["vnets"] = [vnet(HUB, ["10.0.0.0/16"], [subnet(HUB, name, prefix)])]
    d["usages"] = [{"vnet_id": HUB, "value": []}]
    f = by_prefix(capacity.analyze(d), "CAP-SPECIAL-SUBNET-UNDERSIZED:")
    assert [x["severity"] for x in f] == (["medium"] if flagged else [])


def test_vnet_space_fully_allocated_is_low():
    d = healthy()
    d["vnets"] = [vnet(SPK, ["10.1.0.0/24"], [subnet(SPK, "snet-a", "10.1.0.0/25"),
                                             subnet(SPK, "snet-b", "10.1.0.128/25")])]
    f = by_prefix(capacity.analyze(d), "CAP-VNET-SPACE-FULL:")
    assert [x["severity"] for x in f] == ["low"]
    d["vnets"][0]["subnets"].pop()
    assert by_prefix(capacity.analyze(d), "CAP-VNET-SPACE-FULL:") == []


def test_gateway_metrics_cpu_and_limit_based():
    d = healthy()
    d["gateway_metrics"] = [
        {"resource_id": ERGW, "metric": "ExpressRouteGatewayCpuUtilization", "value": 85},
        {"resource_id": VPNGW, "metric": "TunnelAverageBandwidth", "value": 95, "limit": 100,
         "dimensions": {"ConnectionName": "cn-onprem"}},
        {"resource_id": VPNGW, "metric": "AverageBandwidth", "value": 999},          # no limit: ignored
        {"resource_id": VPNGW, "metric": "SomeUnverifiedMetric", "value": 999, "limit": 1}]
    f = by_prefix(capacity.analyze(d), "CAP-GW-METRIC:")
    assert sorted(x["id"] for x in f) == [
        "CAP-GW-METRIC:ergw-hub:ExpressRouteGatewayCpuUtilization",
        "CAP-GW-METRIC:vpngw-hub:TunnelAverageBandwidth:ConnectionName=cn-onprem"]
    assert all(x["severity"] == "high" for x in f)


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = capacity.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) == 2
    assert "subnets_over_threshold" not in r["kpis"]
    d = healthy()
    d["vnets"].append(vnet(HUB, ["10.0.0.0/16"], []))
    assert any("vnet-hub" in g for g in capacity.analyze(d)["evidence_gaps"])
    assert capacity.analyze(healthy())["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    foreign = OTHER + "/resourceGroups/x/providers/Microsoft.Network/virtualNetworks/vnet-x"
    d["usages"].append({"vnet_id": foreign, "value": [usage(foreign + "/subnets/s", 250, 251)]})
    r = capacity.analyze(d)
    assert r["findings"] == []
    assert "1 usages item(s) outside the managed scope were excluded." in r["warnings"]
    d["managed_scopes"] = None
    assert by_prefix(capacity.analyze(d), "CAP-SUBNET-UTIL:")


def test_remediation_scripts_are_human_review_and_commented():
    r = capacity.analyze(load_json(EX / "subnet-exhaustion-input.json"))
    for f in r["findings"]:
        lines = f["remediation_script"].splitlines()
        assert lines[0] == "# Human review required. Read-only verification (the agent never runs writes):"
        for line in lines[1:]:
            if not line.startswith("#"):
                assert guard.classify_az_command(line)["decision"] in ("allow_read", "allow_diagnostic"), line
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        capacity.analyze([])
    with pytest.raises(ValueError):
        capacity.analyze({"usages": {}})
    with pytest.raises(ValueError):
        capacity.analyze({"as_of": "yesterday"})


def test_result_renders_through_adapter():
    r = capacity.analyze(load_json(EX / "subnet-exhaustion-input.json"))
    model = models.build_ip_capacity_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "CAP-SUBNET-UTIL" in html
    with pytest.raises(ValueError):
        models.build_flow_insights_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert capacity.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-ip-capacity"


@pytest.mark.parametrize("command", STEPS_COMMANDS)
def test_skill_steps_commands_are_read_only(command):
    assert guard.classify_az_command(command)["decision"] in ("allow_read", "allow_diagnostic")
