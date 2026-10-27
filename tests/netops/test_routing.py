"""netops-routing-analyzer engine: black holes, peering, asymmetry, NVA forwarding, MTU, gaps, scope."""

import copy
import json
import re

import pytest

from conftest import SKILLS, load_json, load_skill_module

routing = load_skill_module("netops-routing-analyzer", "routing.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

SKILL_DIR = SKILLS / "netops-routing-analyzer"
EX = SKILL_DIR / "examples"
EXAMPLES = ("sc03-blackhole", "sc06-peering", "sc07-ipforward", "mh06-mtu")
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"


def rid(rg, typ, name, sub=SUB):
    return f"{sub}/resourceGroups/{rg}/providers/Microsoft.Network/{typ}/{name}"


HUB = rid("rg-hub", "virtualNetworks", "vnet-hub")
SPOKE = rid("rg-spoke", "virtualNetworks", "vnet-spoke1")
APP_NIC = rid("rg-spoke", "networkInterfaces", "nic-app")
DB_NIC = rid("rg-spoke", "networkInterfaces", "nic-db")
NVA_NIC = rid("rg-hub", "networkInterfaces", "nic-fw")
RT = rid("rg-spoke", "routeTables", "rt-spoke1")
VM = SUB + "/resourceGroups/rg-spoke/providers/Microsoft.Compute/virtualMachines/vm-app"


def eff(prefix, hop, src="Default", ips=None, state="Active"):
    return {"addressPrefix": [prefix], "nextHopType": hop, "nextHopIpAddress": ips or [],
            "source": src, "state": state}


def nic(i, ip, fwd=False):
    return {"id": i, "name": i.rsplit("/", 1)[1], "enableIPForwarding": fwd,
            "ipConfigurations": [{"name": "ipconfig1", "privateIPAddress": ip}]}


def peer(vnet, name, remote, prefix, state="Connected", access=True, fwd=True, gwt=False, urg=False,
         sync="FullyInSync"):
    return {"id": f"{vnet}/virtualNetworkPeerings/{name}", "name": name, "peeringState": state,
            "peeringSyncLevel": sync, "allowVirtualNetworkAccess": access, "allowForwardedTraffic": fwd,
            "allowGatewayTransit": gwt, "useRemoteGateways": urg, "remoteVirtualNetwork": {"id": remote},
            "remoteAddressSpace": {"addressPrefixes": [prefix]}}


def healthy():
    return {
        "managed_scopes": [SUB],
        "route_tables": [{"id": RT, "name": "rt-spoke1", "routes": []}],
        "effective_routes": [{"nic_id": APP_NIC, "value": [eff("10.1.0.0/16", "VnetLocal"),
                                                            eff("10.0.0.0/16", "VNetPeering"),
                                                            eff("0.0.0.0/0", "Internet")]}],
        "vnet_peerings": [{"vnet_id": HUB, "value": [peer(HUB, "hub-to-spoke1", SPOKE, "10.1.0.0/16")]},
                          {"vnet_id": SPOKE, "value": [peer(SPOKE, "spoke1-to-hub", HUB, "10.0.0.0/16")]}],
        "nics": [nic(APP_NIC, "10.1.1.4")],
        "path_checks": [{"path": "app-to-hub", "check": "small", "payload_bytes": 64, "result": "ok"},
                        {"path": "app-to-hub", "check": "large", "payload_bytes": 65536, "result": "ok"}],
    }


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings():
    r = routing.analyze(healthy())
    assert r["skill"] == "netops-routing-analyzer"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"asymmetric_paths": 0}
    assert all(m["tone"] in ("neutral", "good", "warning", "critical") for m in r["metrics"])


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_output_is_deterministic(name):
    data = load_json(EX / f"{name}-input.json")
    expected = load_json(EX / f"{name}-output.json")
    assert routing.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(routing.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_sc03_udr_blackhole_is_critical_and_merges_effective_route():
    r = routing.analyze(load_json(EX / "sc03-blackhole-input.json"))
    [f] = by_prefix(r, "RT-BLACKHOLE:")
    assert f["id"] == "RT-BLACKHOLE:rt-spoke1:sc03-blackhole" and f["severity"] == "critical"
    assert f["evidence"]["addressPrefix"] == "10.100.0.0/16"
    assert f["evidence"]["observed_on"][0]["nic"] == "nic-vm-app"
    assert not by_prefix(r, "RT-BLACKHOLE-EFFECTIVE:")
    assert r["kpis"]["asymmetric_paths"] == 1


def test_effective_only_blackhole_and_default_none_ignored():
    d = healthy()
    d["route_tables"] = []
    d["effective_routes"][0]["value"] += [eff("10.100.0.0/16", "None", src="User"),
                                          eff("10.0.0.0/8", "None"),
                                          eff("10.200.0.0/16", "None", src="User", state="Invalid")]
    r = routing.analyze(d)
    assert [f["severity"] for f in by_prefix(r, "RT-BLACKHOLE-EFFECTIVE:")] == ["critical"]
    assert len(r["findings"]) == 1


def test_next_hop_check_none():
    d = healthy()
    d["next_hop_checks"] = [{"vm_id": VM, "source_ip": "10.1.1.4", "dest_ip": "10.200.1.4",
                             "nextHopType": "None", "nextHopIpAddress": "", "routeTableId": "System Route"}]
    [f] = by_prefix(routing.analyze(d), "RT-NEXTHOP-NONE:")
    assert f["severity"] == "high"
    d["next_hop_checks"][0]["routeTableId"] = RT
    assert by_prefix(routing.analyze(d), "RT-NEXTHOP-NONE:")[0]["severity"] == "critical"


def test_sc06_peering_access_and_forwarded_disabled():
    r = routing.analyze(load_json(EX / "sc06-peering-input.json"))
    [acc] = by_prefix(r, "RT-PEERING-ACCESS-DISABLED:")
    [fwd] = by_prefix(r, "RT-PEERING-FORWARDED-DISABLED:")
    assert acc["severity"] == "critical" and fwd["severity"] == "high"
    assert acc["evidence"]["one_way"] is True
    assert "vnet-spoke1" in acc["id"]


@pytest.mark.parametrize("state,severity", [("Disconnected", "critical"), ("Initiated", "high")])
def test_peering_state(state, severity):
    d = healthy()
    d["vnet_peerings"][1]["value"][0]["peeringState"] = state
    [f] = by_prefix(routing.analyze(d), "RT-PEERING-NOT-CONNECTED:")
    assert f["severity"] == severity


def test_forwarded_traffic_disabled_only_matters_with_transit():
    d = healthy()
    d["vnet_peerings"][1]["value"][0]["allowForwardedTraffic"] = False
    assert not by_prefix(routing.analyze(d), "RT-PEERING-FORWARDED-DISABLED:")
    d["vnet_peerings"][1]["value"][0]["useRemoteGateways"] = True
    assert by_prefix(routing.analyze(d), "RT-PEERING-FORWARDED-DISABLED:")[0]["severity"] == "high"


def test_peering_not_in_sync_is_medium():
    d = healthy()
    d["vnet_peerings"][0]["value"][0]["peeringSyncLevel"] = "RemoteNotInSync"
    [f] = by_prefix(routing.analyze(d), "RT-PEERING-NOT-SYNCED:")
    assert f["severity"] == "medium"
    assert routing.analyze(d)["kpis"]["asymmetric_paths"] == 0


def _flow_input(return_routes):
    d = healthy()
    d["effective_routes"] = [
        {"nic_id": APP_NIC, "value": [eff("10.1.0.0/16", "VnetLocal"),
                                      eff("10.1.2.0/24", "VirtualAppliance", src="User", ips=["10.0.1.4"])]},
        {"nic_id": DB_NIC, "value": [eff("10.1.0.0/16", "VnetLocal")] + return_routes}]
    d["nics"] = [nic(APP_NIC, "10.1.1.4"), nic(DB_NIC, "10.1.2.4"), nic(NVA_NIC, "10.0.1.4", fwd=True)]
    d["flows"] = [{"name": "app-to-db", "source_nic_id": APP_NIC, "destination_ip": "10.1.2.4",
                   "return_nic_id": DB_NIC}]
    return d


def test_asymmetric_return_bypasses_nva():
    r = routing.analyze(_flow_input([]))
    [f] = by_prefix(r, "RT-ASYMMETRIC:")
    assert f["severity"] == "high" and "bypasses" in f["title"]
    assert r["kpis"]["asymmetric_paths"] == 1


def test_asymmetric_different_nva_ips_and_symmetric_ok():
    r = routing.analyze(_flow_input([eff("10.1.1.0/24", "VirtualAppliance", src="User", ips=["10.0.1.5"])]))
    assert "different NVA" in by_prefix(r, "RT-ASYMMETRIC:")[0]["title"]
    r = routing.analyze(_flow_input([eff("10.1.1.0/24", "VirtualAppliance", src="User", ips=["10.0.1.4"])]))
    assert not by_prefix(r, "RT-ASYMMETRIC:")


def test_flow_with_missing_effective_routes_is_gap():
    d = _flow_input([])
    d["effective_routes"] = d["effective_routes"][:1]
    r = routing.analyze(d)
    assert any("flow app-to-db" in g for g in r["evidence_gaps"]) and r["partial"] is True


def test_nva_nic_ip_forwarding_off():
    d = _flow_input([eff("10.1.1.0/24", "VirtualAppliance", src="User", ips=["10.0.1.4"])])
    d["nics"][2]["enableIPForwarding"] = False
    [f] = by_prefix(routing.analyze(d), "RT-NVA-IPFWD-OFF:")
    assert f["id"] == "RT-NVA-IPFWD-OFF:nic-fw" and f["severity"] == "high"
    assert "--ip-forwarding true" in f["remediation_script"]


def test_sc07_dataplane_fails_with_healthy_control_plane():
    r = routing.analyze(load_json(EX / "sc07-ipforward-input.json"))
    [f] = by_prefix(r, "RT-NVA-DATAPLANE:")
    assert f["severity"] == "high"
    assert "data plane fails, control plane healthy" in f["title"]
    assert "guest OS IP forwarding" in f["title"]
    assert not by_prefix(r, "RT-NVA-IPFWD-OFF:")


def test_virtual_appliance_without_path_checks_is_guest_os_gap():
    d = load_json(EX / "sc07-ipforward-input.json")
    del d["path_checks"]
    r = routing.analyze(d)
    assert r["findings"] == [] and r["partial"] is True
    assert any("guest OS forwarding" in g for g in r["evidence_gaps"])
    d["path_checks"] = []
    assert any("guest OS forwarding" in g for g in routing.analyze(d)["evidence_gaps"])


def test_dataplane_failure_with_control_fault_is_path_fail():
    r = routing.analyze(load_json(EX / "sc06-peering-input.json"))
    [f] = by_prefix(r, "RT-PATH-FAIL:")
    assert f["severity"] == "medium" and f["evidence"]["related_findings"]
    assert not by_prefix(r, "RT-NVA-DATAPLANE:")


def test_mh06_mtu_blackhole():
    r = routing.analyze(load_json(EX / "mh06-mtu-input.json"))
    [f] = by_prefix(r, "RT-MTU-BLACKHOLE:")
    assert f["severity"] == "high"
    assert "large payloads fail while small succeed" in f["title"]
    assert "MTU/MSS black-hole" in f["title"]
    assert "-M do -s 1472" in f["remediation_script"]
    assert r["kpis"]["asymmetric_paths"] == 1


def test_payload_size_threshold_and_small_only_gap():
    d = healthy()
    d["path_checks"] = [{"path": "p", "payload_bytes": 100, "result": "Pass"},
                        {"path": "p", "payload_bytes": 9000, "result": "Fail"}]
    assert by_prefix(routing.analyze(d), "RT-MTU-BLACKHOLE:")
    d["path_checks"] = [{"path": "p", "check": "small", "TestResult": "Pass"}]
    r = routing.analyze(d)
    assert r["findings"] == []
    assert any("availability probes measure only small requests" in g for g in r["evidence_gaps"])


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = routing.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) >= 5
    assert "asymmetric_paths" not in r["kpis"]
    d = {k: ([] if isinstance(v, list) else v) for k, v in healthy().items()}
    assert routing.analyze(d)["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    foreign = rid("rg-x", "routeTables", "rt-foreign", sub=OTHER)
    d["route_tables"].append({"id": foreign, "name": "rt-foreign",
                              "routes": [{"name": "drop", "addressPrefix": "10.9.0.0/16", "nextHopType": "None"}]})
    r = routing.analyze(d)
    assert r["findings"] == []
    assert any("outside the managed scope" in w for w in r["warnings"])
    d["managed_scopes"] = None
    assert by_prefix(routing.analyze(d), "RT-BLACKHOLE:")


def test_remediation_scripts_are_human_review_and_commented():
    for name in EXAMPLES:
        for f in routing.analyze(load_json(EX / f"{name}-input.json"))["findings"]:
            script = f["remediation_script"]
            assert script.startswith("# Human review required.")
            for line in script.splitlines():
                if not line.startswith("#"):
                    assert re.search(r"\b(delete|update|create|set|sync|reset)\b", line.split("--query")[0]) is None
            assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        routing.analyze([])
    with pytest.raises(ValueError):
        routing.analyze({"route_tables": {}})
    with pytest.raises(ValueError):
        routing.analyze({"managed_scopes": "x"})


def test_result_renders_through_adapter():
    r = routing.analyze(load_json(EX / "sc03-blackhole-input.json"))
    model = models.build_routing_analyzer_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "RT-BLACKHOLE" in html
    with pytest.raises(ValueError):
        models.build_private_endpoint_dns_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert routing.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-routing-analyzer"


STEP_COMMANDS = (
    "az network route-table list -g rg-spoke -o json",
    "az network nic list -g rg-spoke -o json",
    "az network vnet list -g rg-spoke -o json",
    "az network vnet peering list -g rg-spoke --vnet-name vnet-spoke1 -o json",
    "az network nic show-effective-route-table -g rg-spoke -n nic-app -o json",
    "az network watcher show-next-hop -g rg-spoke --vm vm-app --source-ip 10.1.1.4 --dest-ip 10.100.1.4 -o json",
)


def _skill_az_commands():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    steps = text.split("## Steps", 1)[1].split("## Interpretation", 1)[0]
    return [re.sub(r"<[^>]+>", "x", c) for c in re.findall(r"`(az [^`]+)`", steps)]


def test_step_commands_are_read_only():
    commands = _skill_az_commands()
    assert len(commands) >= 5
    for cmd in commands + list(STEP_COMMANDS):
        verdict = guard.classify_az_command(cmd)
        assert verdict["decision"] in ("allow_read", "allow_diagnostic"), (cmd, verdict)
        assert verdict["allowed"] is True


def test_skill_md_guardrail_and_reference():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.rstrip().endswith("Analysis only — verify against vendor documentation before applying.")
    assert "reference/INDEX.md" in text and "asymmetric_paths" in text
