"""netops-private-endpoint-dns engine: approval, zone group, links, records, resolution, scope."""

import copy
import json

import pytest

from conftest import SKILLS, load_json, load_skill_module

pedns = load_skill_module("netops-private-endpoint-dns", "pedns.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")

EX = SKILLS / "netops-private-endpoint-dns" / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
NET = SUB + "/resourceGroups/rg-spoke/providers/Microsoft.Network"
ZONE_NAME = "privatelink.blob.core.windows.net"
ZONE = SUB + "/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/" + ZONE_NAME
SPOKE = NET + "/virtualNetworks/vnet-spoke1"
HUB = SUB + "/resourceGroups/rg-hub/providers/Microsoft.Network/virtualNetworks/vnet-hub"
PE = NET + "/privateEndpoints/pe-st-blob"
IP = "10.1.2.4"


def pe(status="Approved", group="blob", fqdn="stapp.blob.core.windows.net", rid=PE):
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "properties": {
        "subnet": {"id": SPOKE + "/subnets/snet-pe"},
        "privateLinkServiceConnections": [{"name": "c", "properties": {
            "groupIds": [group], "privateLinkServiceConnectionState": {"status": status}}}],
        "customDnsConfigs": [{"fqdn": fqdn, "ipAddresses": [IP]}]}}


def zone_group(zone_id=ZONE, state="Succeeded", rec="stapp", ips=(IP,), pe_id=PE):
    return {"private_endpoint_id": pe_id, "value": [{"name": "default", "properties": {
        "provisioningState": state,
        "privateDnsZoneConfigs": [{"name": "blob", "properties": {"privateDnsZoneId": zone_id, "recordSets": [
            {"recordType": "A", "recordSetName": rec, "ipAddresses": list(ips)}]}}]}}]}


def link(vnet=SPOKE, name="link-spoke1", state="Completed", policy=None):
    props = {"virtualNetwork": {"id": vnet}, "virtualNetworkLinkState": state, "registrationEnabled": False}
    if policy:
        props["resolutionPolicy"] = policy
    return {"id": ZONE + "/virtualNetworkLinks/" + name, "name": name, "properties": props}


def a_record(name="stapp", ips=(IP,), zone=ZONE):
    return {"id": zone + "/A/" + name, "name": name,
            "properties": {"aRecords": [{"ipv4Address": i} for i in ips]}}


def healthy():
    return {"managed_scopes": [SUB], "private_endpoints": [pe()], "dns_zone_groups": [zone_group()],
            "private_dns_zones": [{"id": ZONE, "name": ZONE_NAME}], "vnet_links": [link()],
            "a_records": [a_record()]}


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def sev(result, prefix):
    return [f["severity"] for f in by_prefix(result, prefix)]


def test_healthy_has_no_findings():
    r = pedns.analyze(healthy())
    assert r["skill"] == "netops-private-endpoint-dns"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and not r["partial"]
    assert r["kpis"] == {"pe_dns_healthy_pct": 100.0}


def test_example_output_is_deterministic():
    data = load_json(EX / "sc05-record-removed-input.json")
    assert pedns.analyze(copy.deepcopy(data)) == load_json(EX / "sc05-record-removed-output.json")


def test_sc05_missing_record_is_critical():
    r = pedns.analyze(load_json(EX / "sc05-record-removed-input.json"))
    assert sev(r, "PE-DNS-RECORD-MISSING:") == ["critical"]
    assert r["kpis"]["pe_dns_healthy_pct"] == 0.0


@pytest.mark.parametrize("status,expected", [("Pending", "high"), ("Rejected", "critical"),
                                             ("Disconnected", "critical")])
def test_connection_states(status, expected):
    d = healthy()
    d["private_endpoints"] = [pe(status)]
    assert sev(pedns.analyze(d), f"PE-CONN-{status.upper()}:") == [expected]


def test_zone_group_failed_and_missing():
    d = healthy()
    d["dns_zone_groups"] = [zone_group(state="Failed")]
    assert sev(pedns.analyze(d), "PE-ZONE-GROUP-FAILED:") == ["high"]
    d["dns_zone_groups"] = []
    assert sev(pedns.analyze(d), "PE-NO-ZONE-GROUP:") in (["medium"], ["high"])


def test_wrong_zone_for_subresource():
    wrong_name = "privatelink.file.core.windows.net"
    wrong = SUB + "/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/" + wrong_name
    d = healthy()
    d["dns_zone_groups"] = [zone_group(zone_id=wrong)]
    d["private_dns_zones"].append({"id": wrong, "name": wrong_name})
    assert sev(pedns.analyze(d), "PE-WRONG-ZONE:") == ["high"]


def test_zone_missing():
    d = healthy()
    d["private_dns_zones"] = []
    assert sev(pedns.analyze(d), "PE-ZONE-MISSING:") == ["high"]


def test_zone_not_linked_to_resolver_vnet_reported_once():
    d = healthy()
    d["resolver_vnets"] = [HUB, SPOKE]
    d["private_endpoints"].append(pe(rid=NET + "/privateEndpoints/pe-two", fqdn="sttwo.blob.core.windows.net"))
    d["dns_zone_groups"].append(zone_group(rec="sttwo", pe_id=NET + "/privateEndpoints/pe-two"))
    d["a_records"].append(a_record("sttwo"))
    r = pedns.analyze(d)
    assert [f["id"] for f in by_prefix(r, "PE-ZONE-NOT-LINKED:")] == [f"PE-ZONE-NOT-LINKED:{ZONE_NAME}:vnet-hub"]


def test_link_not_ready_and_nxdomain_redirect():
    d = healthy()
    d["vnet_links"] = [link(state="InProgress")]
    assert sev(pedns.analyze(d), "PE-LINK-NOT-READY:") == ["medium"]
    d["vnet_links"] = [link(state="Done", policy="NxDomainRedirect")]
    r = pedns.analyze(d)
    assert sev(r, "PE-LINK-NOT-READY:") == []
    assert sev(r, "PE-LINK-NXDOMAIN-REDIRECT:") == ["info"]


def test_record_mismatch():
    d = healthy()
    d["a_records"] = [a_record(ips=("10.1.2.99",))]
    assert sev(pedns.analyze(d), "PE-DNS-RECORD-MISMATCH:") == ["critical"]


def test_expected_record_from_custom_dns_without_zone_group():
    d = healthy()
    d["dns_zone_groups"] = []
    d["a_records"] = []
    r = pedns.analyze(d)
    assert sev(r, "PE-DNS-RECORD-MISSING:") == ["critical"]
    assert by_prefix(r, "PE-DNS-RECORD-MISSING:")[0]["id"].endswith(":stapp")


@pytest.mark.parametrize("ips,prefix,expected", [([], "PE-RESOLVE-NXDOMAIN:", "critical"),
                                                 (["52.239.1.1"], "PE-RESOLVES-PUBLIC:", "critical"),
                                                 (["10.9.9.9"], "PE-RESOLVES-UNKNOWN-IP:", "high"),
                                                 ([IP], "PE-RES", None)])
def test_resolution_checks(ips, prefix, expected):
    d = healthy()
    d["resolution_checks"] = [{"fqdn": "stapp.blob.core.windows.net", "resolved_ips": ips, "from": "vm1"}]
    assert sev(pedns.analyze(d), prefix) == ([expected] if expected else [])


def test_stale_record_is_info_and_non_privatelink_changes_are_silent():
    corp = SUB + "/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/corp.contoso.com"
    d = healthy()
    d["a_records"] += [a_record("old", ips=("10.1.2.50",)), a_record("payments", ips=("10.200.0.10",), zone=corp)]
    d["private_dns_zones"].append({"id": corp, "name": "corp.contoso.com"})
    r = pedns.analyze(d)
    assert [f["severity"] for f in r["findings"]] == ["info"]
    assert r["findings"][0]["id"] == f"PE-DNS-STALE-RECORD:{ZONE_NAME}:old"


def test_absent_inputs_are_gaps():
    r = pedns.analyze({"managed_scopes": [SUB]})
    assert r["partial"] and len(r["evidence_gaps"]) == 5
    d = healthy()
    del d["vnet_links"]
    r = pedns.analyze(d)
    assert r["partial"] and any("vnet_links" in g for g in r["evidence_gaps"])


def test_out_of_scope_dropped_with_warning():
    d = healthy()
    d["private_endpoints"].append(pe("Rejected", rid=OTHER + "/resourceGroups/x/providers/"
                                     "Microsoft.Network/privateEndpoints/pe-foreign"))
    r = pedns.analyze(d)
    assert r["findings"] == []
    assert any("outside the managed scope" in w for w in r["warnings"])


def test_scripts_are_human_review_and_change_lines_commented():
    r = pedns.analyze(load_json(EX / "sc05-record-removed-input.json"))
    for f in r["findings"]:
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])
        if f["remediation_script"]:
            lines = f["remediation_script"].splitlines()
            assert lines[0].startswith("# Human review required.")
            assert not any(" add-record " in ln and not ln.lstrip().startswith("#") for ln in lines)


def test_renders_through_adapter():
    r = pedns.analyze(load_json(EX / "sc05-record-removed-input.json"))
    html = render.render_report(models.build_private_endpoint_dns_model(r, refreshed_at="2025-01-14T08:00:00Z"))
    assert "PE-DNS-RECORD-MISSING" in html


def test_invalid_input_and_cli(tmp_path, capsys):
    with pytest.raises(ValueError):
        pedns.analyze("x")
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert pedns.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-private-endpoint-dns"
