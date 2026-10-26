"""netops-hybrid-health engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json

import pytest

from conftest import SKILLS, load_json, load_skill_module

hybrid = load_skill_module("netops-hybrid-health", "hybrid.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")

EX = SKILLS / "netops-hybrid-health" / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
GW = SUB + "/resourceGroups/rg-hub/providers/Microsoft.Network/virtualNetworkGateways/vpngw-hub"
ERGW = SUB + "/resourceGroups/rg-hub/providers/Microsoft.Network/virtualNetworkGateways/ergw-hub"
CONN = SUB + "/resourceGroups/rg-hub/providers/Microsoft.Network/connections/cn-onprem"
CKT = SUB + "/resourceGroups/rg-er/providers/Microsoft.Network/expressRouteCircuits/er-ckt1"


def gateway(rid=GW, gtype="Vpn", bgp=True):
    return {"id": rid, "name": rid.rsplit("/", 1)[-1],
            "properties": {"gatewayType": gtype, "enableBgp": bgp}}


def connection(status="Connected", tunnels=None, rid=CONN, egress=100, ingress=100):
    props = {"connectionStatus": status, "connectionType": "IPsec",
             "virtualNetworkGateway1": {"id": GW},
             "egressBytesTransferred": egress, "ingressBytesTransferred": ingress}
    if tunnels is not None:
        props["tunnelConnectionStatus"] = tunnels
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "properties": props}


def healthy():
    return {
        "managed_scopes": [SUB],
        "gateways": [gateway()],
        "connections": [connection()],
        "bgp_peers": [{"gateway_id": GW, "value": [{"neighbor": "10.100.0.4", "state": "Connected",
                                                     "asn": 65010, "routesReceived": 3}]}],
        "tunnel_events": [],
        "metrics": [],
    }


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings_and_full_kpis():
    r = hybrid.analyze(healthy())
    assert r["skill"] == "netops-hybrid-health"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"tunnels_connected_pct": 100.0, "bgp_peers_connected_pct": 100.0}


def test_example_output_is_deterministic():
    data = load_json(EX / "sc01-vpn-down-input.json")
    expected = load_json(EX / "sc01-vpn-down-output.json")
    assert hybrid.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(hybrid.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_sc01_routes_to_connection_and_bgp_findings():
    r = hybrid.analyze(load_json(EX / "sc01-vpn-down-input.json"))
    assert any(i.startswith("HYB-CONN-NOT-CONNECTED:") for i in ids(r))
    assert any(i.startswith("HYB-BGP-NOT-CONNECTED:") for i in ids(r))
    assert r["findings"][0]["severity"] == "critical"


@pytest.mark.parametrize("status,severity", [("NotConnected", "critical"), ("Unknown", "critical"),
                                             ("Connecting", "high")])
def test_connection_status_severity(status, severity):
    d = healthy()
    d["connections"] = [connection(status)]
    f = by_prefix(hybrid.analyze(d), "HYB-CONN-NOT-CONNECTED:")
    assert len(f) == 1 and f[0]["severity"] == severity


def test_degraded_tunnel_and_no_traffic():
    d = healthy()
    d["connections"] = [connection(tunnels=[{"tunnel": "t1", "connectionStatus": "Connected"},
                                            {"tunnel": "t2", "connectionStatus": "NotConnected"}])]
    r = hybrid.analyze(d)
    assert [f["severity"] for f in by_prefix(r, "HYB-TUNNEL-DEGRADED:")] == ["medium"]
    d["connections"] = [connection(egress=0, ingress=0)]
    assert [f["severity"] for f in by_prefix(hybrid.analyze(d), "HYB-TUNNEL-NO-TRAFFIC:")] == ["low"]


def test_bgp_metric_fallback_and_gap_when_missing():
    d = healthy()
    del d["bgp_peers"]
    r = hybrid.analyze(d)
    assert any("BGP peer status not collected" in g for g in r["evidence_gaps"]) and r["partial"]
    d["metrics"] = [{"resource_id": GW, "metric": "BgpPeerStatus", "value": 0,
                     "dimensions": {"BgpPeerAddress": "10.100.0.4"}}]
    r = hybrid.analyze(d)
    f = by_prefix(r, "HYB-BGP-NOT-CONNECTED:")
    assert len(f) == 1 and f[0]["severity"] == "critical"
    assert not any("BGP peer status" in g for g in r["evidence_gaps"])


def _event(op, ts, instance="GatewayTenantWorker_IN_0", ip="20.50.0.10"):
    return {"OperationName": op, "remoteIP_s": ip, "instance_s": instance, "TimeGenerated": ts, "ResourceId": GW}


def test_flap_detection_threshold():
    d = healthy()
    events = []
    for i in range(3):
        events.append(_event("TunnelDisconnected", f"2025-01-14T07:{i * 10:02d}:00Z"))
        events.append(_event("TunnelConnected", f"2025-01-14T07:{i * 10 + 1:02d}:00Z"))
    d["tunnel_events"] = events
    f = by_prefix(hybrid.analyze(d), "HYB-TUNNEL-FLAP:")
    assert len(f) == 1 and f[0]["severity"] == "high"
    d["tunnel_events"] = events[:2]
    assert by_prefix(hybrid.analyze(d), "HYB-TUNNEL-FLAP:") == [] or \
        all(x["severity"] != "high" for x in by_prefix(hybrid.analyze(d), "HYB-TUNNEL-FLAP:"))


def test_flap_without_reconnect_is_high():
    d = healthy()
    d["tunnel_events"] = [_event("TunnelDisconnected", "2025-01-14T07:00:00Z")]
    f = by_prefix(hybrid.analyze(d), "HYB-TUNNEL-FLAP:")
    assert len(f) == 1 and f[0]["severity"] == "high"


def test_traffic_selector_mismatch():
    d = healthy()
    d["metrics"] = [{"resource_id": GW, "metric": "TunnelEgressPacketDropTSMismatch", "value": 42,
                     "dimensions": {"ConnectionName": "cn-onprem"}},
                    {"resource_id": GW, "metric": "TunnelIngressPacketDropTSMismatch", "value": 0,
                     "dimensions": {"ConnectionName": "cn-onprem"}}]
    f = by_prefix(hybrid.analyze(d), "HYB-TS-MISMATCH:")
    assert len(f) == 1 and f[0]["severity"] == "high"


def test_expressroute_states_metrics_and_route_limit():
    d = healthy()
    d["gateways"].append(gateway(ERGW, "ExpressRoute", bgp=False))
    d["er_circuits"] = [{"id": CKT, "name": "er-ckt1", "sku": {"tier": "Standard"},
                         "properties": {"serviceProviderProvisioningState": "Provisioned",
                                        "circuitProvisioningState": "Enabled"}}]
    d["er_route_summaries"] = [
        {"circuit_id": CKT, "peering": "AzurePrivatePeering", "path": "primary",
         "value": [{"neighbor": "10.255.0.1", "as": 65020, "statePfxRcd": "3500", "upDown": "1d"}]},
        {"circuit_id": CKT, "peering": "AzurePrivatePeering", "path": "secondary",
         "value": [{"neighbor": "10.255.0.5", "as": 65020, "statePfxRcd": "Idle", "upDown": "5m"}]}]
    d["metrics"] = [{"resource_id": CKT, "metric": "BgpAvailability", "value": 50,
                     "dimensions": {"PeeringType": "AzurePrivatePeering", "Peer": "Secondary"}}]
    r = hybrid.analyze(d)
    assert [f["severity"] for f in by_prefix(r, "HYB-ER-ROUTE-LIMIT:")] == ["high"]
    assert [f["severity"] for f in by_prefix(r, "HYB-ER-BGP-DOWN:")] == ["critical"]
    assert [f["severity"] for f in by_prefix(r, "HYB-ER-BGPAVAILABILITY:")] == ["high"]
    d["er_circuits"][0]["sku"]["tier"] = "Premium"
    assert by_prefix(hybrid.analyze(d), "HYB-ER-ROUTE-LIMIT:") == []


@pytest.mark.parametrize("sp,state,prefix", [("NotProvisioned", "Enabled", "HYB-ER-NOT-PROVISIONED:"),
                                             ("Provisioned", "Disabled", "HYB-ER-CIRCUIT-DISABLED:")])
def test_expressroute_circuit_state(sp, state, prefix):
    d = healthy()
    d["er_circuits"] = [{"id": CKT, "name": "er-ckt1", "properties": {
        "serviceProviderProvisioningState": sp, "circuitProvisioningState": state}}]
    d["er_route_summaries"] = []
    assert [f["severity"] for f in by_prefix(hybrid.analyze(d), prefix)] == ["critical"]


def test_er_gateway_without_circuits_is_a_gap():
    d = healthy()
    d["gateways"].append(gateway(ERGW, "ExpressRoute", bgp=False))
    assert any("er_circuits not collected" in g for g in hybrid.analyze(d)["evidence_gaps"])


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = hybrid.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) >= 3
    assert hybrid.analyze(healthy())["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    d["connections"].append(connection("NotConnected", rid=OTHER + "/resourceGroups/x/providers/"
                                       "Microsoft.Network/connections/cn-foreign"))
    r = hybrid.analyze(d)
    assert r["findings"] == []
    assert any("outside the managed scope" in w for w in r["warnings"])
    d["managed_scopes"] = None
    assert by_prefix(hybrid.analyze(d), "HYB-CONN-NOT-CONNECTED:")


def test_remediation_scripts_are_human_review_and_commented():
    r = hybrid.analyze(load_json(EX / "sc01-vpn-down-input.json"))
    for f in r["findings"]:
        script = f["remediation_script"]
        assert script.startswith("# Human review required.")
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        hybrid.analyze([])
    with pytest.raises(ValueError):
        hybrid.analyze({"connections": {}})


def test_result_renders_through_adapter():
    r = hybrid.analyze(load_json(EX / "sc01-vpn-down-input.json"))
    model = models.build_hybrid_health_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "HYB-CONN-NOT-CONNECTED" in html
    with pytest.raises(ValueError):
        models.build_private_endpoint_dns_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert hybrid.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-hybrid-health"
