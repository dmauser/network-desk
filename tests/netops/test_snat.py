"""netops-snat-egress engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json
import re

import pytest

from conftest import SKILLS, load_json, load_skill_module

snat = load_skill_module("netops-snat-egress", "snat.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

SKILL_DIR = SKILLS / "netops-snat-egress"
EX = SKILL_DIR / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
LB = SUB + "/resourceGroups/rg-netops-spoke/providers/Microsoft.Network/loadBalancers/lb-egress"
NAT = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.Network/natGateways/natgw-hub"

# Every az command listed in SKILL.md "Steps" (placeholders kept as written).
STEPS_COMMANDS = (
    "az network lb list -g <rg> -o json",
    "az network lb outbound-rule list -g <rg> --lb-name <lb> -o json",
    "az network nat gateway list -g <rg> -o json",
    "az monitor metrics list --resource <lb-id> --metrics UsedSnatPorts AllocatedSnatPorts --aggregation Average "
    "--interval PT1M --dimension BackendIPAddress -o json",
    "az monitor metrics list --resource <lb-id> --metrics SnatConnectionCount --aggregation Total --interval PT1M "
    "--dimension ConnectionState BackendIPAddress -o json",
    "az monitor metrics list --resource <lb-id> --metrics VipAvailability DipAvailability --aggregation Average "
    "--interval PT5M --dimension FrontendIPAddress -o json",
    "az monitor metrics list --resource <natgw-id> --metrics SNATConnectionCount --aggregation Total --interval PT1M "
    "--dimension ConnectionState -o json",
    "az monitor metrics list --resource <natgw-id> --metrics PacketDropCount TotalConnectionCount --aggregation Total "
    "--interval PT1M -o json",
    "az monitor metrics list --resource <natgw-id> --metrics DatapathAvailability --aggregation Average "
    "--interval PT5M -o json",
)

CHANGE_RE = re.compile(r"^az\s+.*\b(create|update|delete|set|add|remove)\b")


def lb(outbound_ports=1024, outbound_rules=True, lb_rules=None, rid=LB, public=True, pool=2):
    fe = {"id": rid + "/frontendIPConfigurations/fe1", "name": "fe1"}
    if public:
        fe["publicIPAddress"] = {"id": SUB + "/resourceGroups/rg-netops-spoke/providers/"
                                       "Microsoft.Network/publicIPAddresses/pip-lb"}
    rules = []
    if outbound_rules:
        rules = [{"id": rid + "/outboundRules/or1", "name": "or1", "allocatedOutboundPorts": outbound_ports,
                  "protocol": "All", "frontendIPConfigurations": [{"id": fe["id"]}],
                  "backendAddressPool": {"id": rid + "/backendAddressPools/bp1"}}]
    return {"id": rid, "name": rid.rsplit("/", 1)[-1],
            "frontendIPConfigurations": [fe],
            "backendAddressPools": [{"id": rid + "/backendAddressPools/bp1", "name": "bp1",
                                     "backendIPConfigurations": [{"id": f"nic{i}"} for i in range(pool)]}],
            "loadBalancingRules": lb_rules or [],
            "outboundRules": rules}


def nat(idle=4, rid=NAT):
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "idleTimeoutInMinutes": idle,
            "publicIpAddresses": [{"id": "pip"}], "publicIpPrefixes": [], "subnets": [{"id": "snet"}]}


def m(rid, metric, value, agg="Average", **dims):
    return {"resource_id": rid, "metric": metric, "value": value, "aggregation": agg, "dimensions": dims}


def healthy():
    return {
        "managed_scopes": [SUB],
        "load_balancers": [lb()],
        "nat_gateways": [nat()],
        "metrics": [
            m(LB, "AllocatedSnatPorts", 1024, BackendIPAddress="10.1.0.4"),
            m(LB, "UsedSnatPorts", 200, BackendIPAddress="10.1.0.4"),
            m(LB, "SnatConnectionCount", 0, "Total", ConnectionState="Failed", BackendIPAddress="10.1.0.4"),
            m(LB, "VipAvailability", 100, FrontendIPAddress="20.0.0.1"),
            m(NAT, "SNATConnectionCount", 5000, "Total", ConnectionState="Attempted"),
            m(NAT, "SNATConnectionCount", 0, "Total", ConnectionState="Failed"),
            m(NAT, "PacketDropCount", 0, "Total"),
            m(NAT, "DatapathAvailability", 100),
        ],
    }


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def sev(result, prefix):
    return [f["severity"] for f in by_prefix(result, prefix)]


def test_healthy_has_no_findings_and_kpi():
    r = snat.analyze(healthy())
    assert r["skill"] == "netops-snat-egress"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"snat_peak_util_pct": 19.5}


@pytest.mark.parametrize("name", ["snat-exhaustion", "natgw-drops"])
def test_example_output_is_deterministic(name):
    data = load_json(EX / f"{name}-input.json")
    expected = load_json(EX / f"{name}-output.json")
    assert snat.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(snat.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_snat_exhaustion_example():
    r = snat.analyze(load_json(EX / "snat-exhaustion-input.json"))
    assert r["findings"][0]["severity"] == "critical"
    assert by_prefix(r, "SNAT-LB-PORT-UTIL:") and by_prefix(r, "SNAT-LB-FAILED-CONN:")
    assert r["kpis"]["snat_peak_util_pct"] == 97.8


@pytest.mark.parametrize("used,severity", [(700, []), (720, ["high"]), (870, ["critical"]), (1024, ["critical"])])
def test_port_utilization_thresholds(used, severity):
    d = healthy()
    d["metrics"][1]["value"] = used
    r = snat.analyze(d)
    assert sev(r, "SNAT-LB-PORT-UTIL:") == severity
    assert r["kpis"]["snat_peak_util_pct"] == round(100.0 * used / 1024, 1)


def test_port_utilization_uses_peak_and_custom_thresholds():
    d = healthy()
    d["metrics"].append(m(LB, "UsedSnatPorts", 600, BackendIPAddress="10.1.0.4"))
    d["thresholds"] = {"snat_warn_pct": 50, "snat_crit_pct": 90}
    r = snat.analyze(d)
    assert sev(r, "SNAT-LB-PORT-UTIL:") == ["high"]
    assert r["kpis"]["snat_peak_util_pct"] == 58.6


@pytest.mark.parametrize("failed,severity", [(1, "high"), (999, "high"), (1000, "critical")])
def test_lb_failed_connections(failed, severity):
    d = healthy()
    d["metrics"][2]["value"] = failed
    assert sev(snat.analyze(d), "SNAT-LB-FAILED-CONN:") == [severity]


def test_nat_failed_drops_and_idle_timeout():
    d = healthy()
    d["nat_gateways"] = [nat(idle=30)]
    d["metrics"][6]["value"] = 50
    r = snat.analyze(d)
    assert sev(r, "SNAT-NAT-PACKET-DROPS:") == ["medium"]
    assert sev(r, "SNAT-NAT-IDLE-TIMEOUT:") == ["low"]
    d["metrics"][5]["value"] = 2000
    r = snat.analyze(d)
    assert sev(r, "SNAT-NAT-FAILED-CONN:") == ["critical"]
    assert sev(r, "SNAT-NAT-PACKET-DROPS:") == ["high"]
    d["nat_gateways"] = [nat(idle=4)]
    assert sev(snat.analyze(d), "SNAT-NAT-IDLE-TIMEOUT:") == []


@pytest.mark.parametrize("value,severity", [(100, []), (99.2, ["high"]), (0, ["critical"])])
def test_nat_datapath_availability(value, severity):
    d = healthy()
    d["metrics"][7]["value"] = value
    assert sev(snat.analyze(d), "SNAT-NAT-DATAPATHAVAILABILITY:") == severity


def test_lb_vip_and_dip_availability():
    d = healthy()
    d["metrics"][3]["value"] = 0
    d["metrics"].append(m(LB, "DipAvailability", 50, BackendIPAddress="10.1.0.4", BackendPort="443"))
    r = snat.analyze(d)
    assert sev(r, "SNAT-LB-VIPAVAILABILITY:") == ["critical"]
    assert sev(r, "SNAT-LB-DIPAVAILABILITY:") == ["medium"]


def test_outbound_rule_port_allocation():
    d = healthy()
    d["load_balancers"] = [lb(outbound_ports=0)]
    assert sev(snat.analyze(d), "SNAT-LB-DEFAULT-PORTS:") == ["medium"]
    d["load_balancers"] = [lb(outbound_ports=256)]
    f = by_prefix(snat.analyze(d), "SNAT-LB-LOW-PORTS:")
    assert [x["severity"] for x in f] == ["low"]
    assert f[0]["evidence"]["max_ports_per_instance"] == 32000


def test_lb_rule_default_snat():
    d = healthy()
    d["load_balancers"] = [lb(outbound_rules=False, lb_rules=[
        {"id": LB + "/loadBalancingRules/r1", "name": "r1", "disableOutboundSnat": False},
        {"id": LB + "/loadBalancingRules/r2", "name": "r2", "disableOutboundSnat": True}])]
    f = by_prefix(snat.analyze(d), "SNAT-LB-RULE-DEFAULT-SNAT:")
    assert [x["severity"] for x in f] == ["medium"]
    assert f[0]["evidence"]["loadBalancingRules_with_outbound_snat"] == ["r1"]


def test_internal_lb_is_ignored():
    d = healthy()
    d["load_balancers"] = [lb(public=False, outbound_rules=False,
                              lb_rules=[{"name": "r1", "disableOutboundSnat": False}])]
    d["metrics"] = [x for x in d["metrics"] if x["resource_id"] == NAT]
    r = snat.analyze(d)
    assert r["findings"] == [] and r["evidence_gaps"] == []


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = snat.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) == 3
    assert "kpis" in r and r["kpis"] == {}
    r = snat.analyze({"managed_scopes": [SUB], "load_balancers": [], "nat_gateways": [], "metrics": []})
    assert r["evidence_gaps"] == [] and r["partial"] is False


def test_missing_metrics_for_resources_are_gaps():
    d = healthy()
    d["metrics"] = []
    r = snat.analyze(d)
    assert any("UsedSnatPorts" in g and "lb-egress" in g for g in r["evidence_gaps"])
    assert any("SNATConnectionCount" in g and "natgw-hub" in g for g in r["evidence_gaps"])
    assert r["partial"] is True


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    foreign_nat = OTHER + "/resourceGroups/x/providers/Microsoft.Network/natGateways/natgw-foreign"
    d["nat_gateways"].append(nat(rid=foreign_nat))
    d["metrics"].append(m(foreign_nat, "SNATConnectionCount", 500, "Total", ConnectionState="Failed"))
    r = snat.analyze(d)
    assert r["findings"] == []
    assert "1 nat_gateways item(s) outside the managed scope were excluded." in r["warnings"]
    assert "1 metrics item(s) outside the managed scope were excluded." in r["warnings"]
    d["managed_scopes"] = None
    r = snat.analyze(d)
    assert sev(r, "SNAT-NAT-FAILED-CONN:") == ["high"] and r["warnings"] == []


@pytest.mark.parametrize("name", ["snat-exhaustion", "natgw-drops"])
def test_remediation_scripts_are_human_review_and_commented(name):
    r = snat.analyze(load_json(EX / f"{name}-input.json"))
    d = healthy()
    d["load_balancers"] = [lb(outbound_ports=0), lb(outbound_rules=False, rid=LB + "2", lb_rules=[
        {"name": "r1", "disableOutboundSnat": False}])]
    findings = r["findings"] + snat.analyze(d)["findings"]
    assert findings
    for f in findings:
        lines = f["remediation_script"].splitlines()
        assert lines[0] == "# Human review required. Read-only verification (the agent never runs writes):"
        for idx, line in enumerate(lines):
            if line.startswith("az "):
                assert not CHANGE_RE.match(line), line
                assert guard.classify_az_command(line)["decision"] in ("allow_read", "allow_diagnostic"), line
            if line.startswith("# az ") and CHANGE_RE.match(line[2:]):
                assert "# Change (review before running):" in lines[:idx]
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])


def test_findings_sorted_and_ids_stable():
    r = snat.analyze(load_json(EX / "natgw-drops-input.json"))
    order = ("critical", "high", "medium", "low", "info")
    keys = [(order.index(f["severity"]), f["resource_id"].casefold(), f["id"]) for f in r["findings"]]
    assert keys == sorted(keys)
    assert all(f["skill"] == "netops-snat-egress" for f in r["findings"])


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        snat.analyze([])
    with pytest.raises(ValueError):
        snat.analyze({"metrics": {}})
    with pytest.raises(ValueError):
        snat.analyze({"load_balancers": "lb"})


def test_result_renders_through_adapter():
    r = snat.analyze(load_json(EX / "snat-exhaustion-input.json"))
    model = models.build_snat_egress_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "SNAT-LB-PORT-UTIL" in html
    with pytest.raises(ValueError):
        models.build_hybrid_health_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert snat.main([str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-snat-egress"


PLACEHOLDERS = {"<rg>": "rg-netops-spoke", "<lb>": "lb-egress", "<lb-id>": LB, "<natgw-id>": NAT}


def concrete(command):
    for placeholder, value in PLACEHOLDERS.items():
        command = command.replace(placeholder, value)
    assert "<" not in command and ">" not in command
    return command


@pytest.mark.parametrize("command", STEPS_COMMANDS)
def test_steps_commands_are_read_only(command):
    assert guard.classify_az_command(concrete(command))["decision"] in ("allow_read", "allow_diagnostic")


def test_steps_commands_match_skill_md():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    steps = text.split("## Steps", 1)[1].split("## Interpretation", 1)[0]
    listed = [" ".join(c.split()) for c in re.findall(r"`(az [^`]+)`", steps)]
    assert sorted(listed) == sorted(" ".join(c.split()) for c in STEPS_COMMANDS)
    assert text.rstrip().endswith("Analysis only — verify against vendor documentation before applying.")
