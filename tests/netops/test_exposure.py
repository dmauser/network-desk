"""netops-exposure-scan engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json
import re

import pytest

from conftest import SKILLS, load_json, load_skill_module

exposure = load_skill_module("netops-exposure-scan", "exposure.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

SKILL_DIR = SKILLS / "netops-exposure-scan"
EX = SKILL_DIR / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
N = SUB + "/resourceGroups/rg-app/providers/Microsoft.Network"
P = SUB + "/resourceGroups/rg-app/providers"
SUBNET = N + "/virtualNetworks/vnet/subnets/snet-web"
NIC = N + "/networkInterfaces/nic-web"
PIP = N + "/publicIPAddresses/pip-web"
SUBNET_NSG = N + "/networkSecurityGroups/nsg-subnet"
NIC_NSG = N + "/networkSecurityGroups/nsg-nic"

# Every az command listed in SKILL.md "Steps" (placeholders kept as written).
STEPS_COMMANDS = (
    "az network public-ip list -o json",
    "az network nic list -o json",
    "az network nsg list -o json",
    "az network application-gateway list -o json",
    "az network application-gateway waf-policy list -o json",
    "az storage account list -o json",
    "az keyvault list -o json",
    "az keyvault show -n <kv> -o json",
    "az sql server list -o json",
    "az network bastion list -o json",
    "az network nic list-effective-nsg -g <rg> -n <nic> -o json",
)

CHANGE_RE = re.compile(r"^az\s+.*\b(create|update|delete|set|add|remove)\b")
END = "Analysis only — verify against vendor documentation before applying."


def concrete(command):
    return re.sub(r"<[^>]+>", "x", command)


def rule(nsg_id, name, priority, access="Allow", protocol="Tcp", src="Internet", ports=("443",), dst="*",
         direction="Inbound", sport="*", dst_asgs=None):
    props = {"priority": priority, "direction": direction, "access": access, "protocol": protocol,
             "sourceAddressPrefix": src, "sourcePortRange": sport, "destinationAddressPrefix": dst,
             "destinationPortRanges": list(ports)}
    if dst_asgs:
        props["destinationApplicationSecurityGroups"] = [{"id": a} for a in dst_asgs]
    return {"id": f"{nsg_id}/securityRules/{name}", "name": name, "properties": props}


def nsg(rid, rules, subnets=()):
    return {"id": rid, "name": rid.rsplit("/", 1)[-1],
            "properties": {"securityRules": rules, "subnets": [{"id": s} for s in subnets]}}


def pip(rid=PIP, sku="Standard", attached=NIC + "/ipConfigurations/ipconfig1", nat=None):
    props = {"ipAddress": "20.0.0.10"}
    if attached:
        props["ipConfiguration"] = {"id": attached}
    if nat:
        props["natGateway"] = {"id": nat}
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "sku": {"name": sku}, "properties": props}


def nic(rid=NIC, public=PIP, nsg_id=None, private="10.0.1.4", asgs=None):
    cfg = {"privateIPAddress": private, "subnet": {"id": SUBNET}}
    if public:
        cfg["publicIPAddress"] = {"id": public}
    if asgs:
        cfg["applicationSecurityGroups"] = [{"id": a} for a in asgs]
    props = {"ipConfigurations": [{"id": rid + "/ipConfigurations/ipconfig1", "name": "ipconfig1",
                                   "properties": cfg}]}
    if nsg_id:
        props["networkSecurityGroup"] = {"id": nsg_id}
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "properties": props}


def healthy():
    return {
        "managed_scopes": [SUB],
        "public_ips": [pip()],
        "nics": [nic()],
        "nsgs": [nsg(SUBNET_NSG, [rule(SUBNET_NSG, "allow-ssh-corp", 200, src="203.0.113.0/24", ports=("22",))],
                     subnets=(SUBNET,))],
        "app_gateways": [],
        "paas_resources": [],
    }


def with_rules(rules, nic_rules=None):
    d = healthy()
    d["nsgs"] = [nsg(SUBNET_NSG, rules, subnets=(SUBNET,))]
    if nic_rules is not None:
        d["nsgs"].append(nsg(NIC_NSG, nic_rules))
        d["nics"] = [nic(nsg_id=NIC_NSG)]
    return d


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings():
    r = exposure.analyze(healthy())
    assert r["skill"] == "netops-exposure-scan"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"risky_mgmt_exposures": 0}
    for m in r["metrics"]:
        assert m["tone"] in ("neutral", "good", "warning", "critical")


def test_example_output_is_deterministic():
    data = load_json(EX / "internet-exposure-input.json")
    expected = load_json(EX / "internet-exposure-output.json")
    assert exposure.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(exposure.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_example_findings():
    r = exposure.analyze(load_json(EX / "internet-exposure-input.json"))
    sev = {f["id"]: f["severity"] for f in r["findings"]}
    assert sev == {
        "EXP-MGMT-EXPOSED:nic-vm-jump:22": "critical",
        "EXP-MGMT-EXPOSED:nic-vm-jump:3389": "critical",
        "EXP-APPGW-NO-WAF:agw-netops": "high",
        "EXP-PAAS-OPEN:stnetopsdata": "high",
        "EXP-PORT-EXPOSED:nic-vm-jump": "medium",
        "EXP-PAAS-FIREWALLED:kv-netops": "low",
        "EXP-PIP-UNATTACHED:pip-orphan": "low",
    }
    assert r["kpis"] == {"risky_mgmt_exposures": 2}
    assert by_prefix(r, "EXP-PORT-EXPOSED:")[0]["evidence"]["openPorts"] == {"TCP": "443"}


@pytest.mark.parametrize("port", [22, 3389, 5985, 5986])
def test_mgmt_port_exposed_is_critical(port):
    r = exposure.analyze(with_rules([rule(SUBNET_NSG, "allow-mgmt", 200, src="*", ports=(str(port),))]))
    f = by_prefix(r, "EXP-MGMT-EXPOSED:")
    assert [x["id"] for x in f] == [f"EXP-MGMT-EXPOSED:nic-web:{port}"]
    assert f[0]["severity"] == "critical" and r["kpis"]["risky_mgmt_exposures"] == 1
    assert not by_prefix(r, "EXP-PORT-EXPOSED:")


def test_both_subnet_and_nic_nsg_must_allow():
    subnet_rules = [rule(SUBNET_NSG, "allow-web-ssh", 200, ports=("22", "443"))]
    nic_rules = [rule(NIC_NSG, "allow-web", 200, ports=("443",))]
    r = exposure.analyze(with_rules(subnet_rules, nic_rules))
    assert not by_prefix(r, "EXP-MGMT-EXPOSED:")
    f = by_prefix(r, "EXP-PORT-EXPOSED:")
    assert [x["id"] for x in f] == ["EXP-PORT-EXPOSED:nic-web"] and f[0]["severity"] == "medium"
    assert f[0]["evidence"]["nsgPath"] == ["subnet:nsg-subnet", "nic:nsg-nic"]


def test_higher_priority_deny_wins():
    r = exposure.analyze(with_rules([rule(SUBNET_NSG, "deny-ssh", 100, "Deny", src="*", ports=("22",)),
                                     rule(SUBNET_NSG, "allow-all", 200, protocol="*", src="Internet", ports=("*",))]))
    assert not by_prefix(r, "EXP-MGMT-EXPOSED:nic-web:22")
    assert by_prefix(r, "EXP-MGMT-EXPOSED:nic-web:3389")
    f = by_prefix(r, "EXP-PORT-EXPOSED:")[0]
    assert f["evidence"]["openPorts"] == {"TCP": "0-21,23-3388,3390-5984,5987-65535", "UDP": "*"}


def test_deny_limited_to_source_ports_does_not_block():
    r = exposure.analyze(with_rules([rule(SUBNET_NSG, "deny-ssh", 100, "Deny", src="*", ports=("22",), sport="1024"),
                                     rule(SUBNET_NSG, "allow-ssh", 200, src="*", ports=("22",))]))
    assert by_prefix(r, "EXP-MGMT-EXPOSED:nic-web:22")


def test_destination_matching_private_ip_and_asg():
    asg = N + "/applicationSecurityGroups/asg-web"
    d = with_rules([rule(SUBNET_NSG, "allow-ssh-other-host", 200, src="*", ports=("22",), dst="10.0.9.0/24"),
                    rule(SUBNET_NSG, "allow-rdp-host", 210, src="*", ports=("3389",), dst="10.0.1.4/32"),
                    rule(SUBNET_NSG, "allow-winrm-asg", 220, src="*", ports=("5986",), dst="", dst_asgs=[asg])])
    d["nics"] = [nic(asgs=[asg])]
    r = exposure.analyze(d)
    assert sorted(ids(r)) == ["EXP-MGMT-EXPOSED:nic-web:3389", "EXP-MGMT-EXPOSED:nic-web:5986"]


def test_trusted_source_and_default_rules_are_not_exposure():
    d = with_rules([rule(SUBNET_NSG, "allow-corp", 200, src="203.0.113.0/24", ports=("*",)),
                    rule(SUBNET_NSG, "allow-vnet", 210, src="VirtualNetwork", ports=("*",))])
    assert exposure.analyze(d)["findings"] == []


def test_standard_pip_without_nsg_is_closed_basic_is_open():
    d = healthy()
    d["nsgs"] = []
    r = exposure.analyze(d)
    assert r["findings"] == [] and r["kpis"] == {"risky_mgmt_exposures": 0}
    d["public_ips"] = [pip(sku="Basic")]
    r = exposure.analyze(d)
    assert sorted(ids(r)) == ["EXP-MGMT-EXPOSED:nic-web:22", "EXP-MGMT-EXPOSED:nic-web:3389",
                              "EXP-MGMT-EXPOSED:nic-web:5985", "EXP-MGMT-EXPOSED:nic-web:5986",
                              "EXP-PIP-BASIC:pip-web", "EXP-PORT-EXPOSED:nic-web"]
    assert by_prefix(r, "EXP-PIP-BASIC:")[0]["severity"] == "low"
    assert r["kpis"]["risky_mgmt_exposures"] == 4


def test_nic_without_public_ip_is_ignored():
    d = with_rules([rule(SUBNET_NSG, "allow-all", 100, protocol="*", src="*", ports=("*",))])
    d["nics"] = [nic(public=None)]
    assert by_prefix(exposure.analyze(d), "EXP-MGMT-") == []


def test_missing_nic_nsg_is_a_gap():
    d = healthy()
    d["nics"] = [nic(nsg_id=NIC_NSG)]
    r = exposure.analyze(d)
    assert r["partial"] is True and any("nsg-nic" in g for g in r["evidence_gaps"])


def test_unattached_pip():
    d = healthy()
    d["public_ips"].append(pip(rid=N + "/publicIPAddresses/pip-free", attached=None))
    d["public_ips"].append(pip(rid=N + "/publicIPAddresses/pip-nat", attached=None, nat=N + "/natGateways/ng"))
    f = by_prefix(exposure.analyze(d), "EXP-PIP-UNATTACHED:")
    assert [x["id"] for x in f] == ["EXP-PIP-UNATTACHED:pip-free"] and f[0]["severity"] == "low"


def agw(tier, policy=None, wafc=None, public=True):
    fe = {"name": "fe", "properties": {}}
    if public:
        fe["properties"]["publicIPAddress"] = {"id": N + "/publicIPAddresses/pip-agw"}
    else:
        fe["properties"]["privateIPAddress"] = "10.0.2.10"
    props = {"sku": {"name": tier, "tier": tier}, "frontendIPConfigurations": [fe]}
    if policy:
        props["firewallPolicy"] = {"id": policy}
    if wafc is not None:
        props["webApplicationFirewallConfiguration"] = wafc
    return {"id": N + "/applicationGateways/agw", "name": "agw", "properties": props}


@pytest.mark.parametrize("gw,expected", [
    (agw("Standard_v2"), ("EXP-APPGW-NO-WAF:agw", "high")),
    (agw("WAF_v2"), ("EXP-APPGW-NO-WAF:agw", "high")),
    (agw("WAF_v2", wafc={"enabled": False}), ("EXP-APPGW-NO-WAF:agw", "high")),
    (agw("WAF_v2", policy=N + "/ApplicationGatewayWebApplicationFirewallPolicies/waf"), None),
    (agw("WAF_v2", wafc={"enabled": True, "firewallMode": "Prevention"}), None),
    (agw("WAF_v2", wafc={"enabled": True, "firewallMode": "Detection"}), ("EXP-APPGW-WAF-DETECTION:agw", "medium")),
    (agw("Standard_v2", public=False), None),
])
def test_app_gateway_waf(gw, expected):
    d = healthy()
    d["app_gateways"] = [gw]
    found = [(f["id"], f["severity"]) for f in by_prefix(exposure.analyze(d), "EXP-APPGW-")]
    assert found == ([expected] if expected else [])


def storage(pna="Enabled", action="Allow", rules=0, name="st1"):
    return {"id": P + f"/Microsoft.Storage/storageAccounts/{name}", "name": name,
            "type": "Microsoft.Storage/storageAccounts", "publicNetworkAccess": pna,
            "networkRuleSet": {"defaultAction": action, "ipRules": [{"ipAddressOrRange": "203.0.113.1"}] * rules,
                               "virtualNetworkRules": []}}


@pytest.mark.parametrize("res,expected", [
    (storage(), ("EXP-PAAS-OPEN:st1", "high")),
    (storage(pna=None), ("EXP-PAAS-OPEN:st1", "high")),
    (storage(pna="Disabled"), None),
    (storage(pna="SecuredByPerimeter"), None),
    (storage(action="Deny", rules=2), ("EXP-PAAS-FIREWALLED:st1", "low")),
    (storage(action="Deny"), ("EXP-PAAS-FIREWALLED:st1", "info")),
    ({"id": P + "/Microsoft.KeyVault/vaults/kv1", "name": "kv1", "type": "Microsoft.KeyVault/vaults",
      "properties": {"publicNetworkAccess": "Enabled", "networkAcls": {"defaultAction": "Allow"}}},
     ("EXP-PAAS-OPEN:kv1", "high")),
    ({"id": P + "/Microsoft.KeyVault/vaults/kv1", "name": "kv1", "type": "Microsoft.KeyVault/vaults",
      "properties": {"publicNetworkAccess": "Enabled"}}, ("EXP-PAAS-OPEN:kv1", "medium")),
    ({"id": P + "/Microsoft.KeyVault/vaults/kv1", "name": "kv1", "type": "Microsoft.KeyVault/vaults",
      "properties": {"publicNetworkAccess": "disabled", "networkAcls": {"defaultAction": "Allow"}}}, None),
    ({"id": P + "/Microsoft.Sql/servers/sql1", "name": "sql1", "type": "Microsoft.Sql/servers",
      "publicNetworkAccess": "Enabled"}, ("EXP-SQL-PUBLIC:sql1", "low")),
    ({"id": P + "/Microsoft.Sql/servers/sql1", "name": "sql1", "type": "Microsoft.Sql/servers",
      "publicNetworkAccess": "Disabled"}, None),
])
def test_paas_public_network_access(res, expected):
    d = healthy()
    if res.get("publicNetworkAccess", "x") is None:
        del res["publicNetworkAccess"]
    d["paas_resources"] = [res]
    found = [(f["id"], f["severity"]) for f in exposure.analyze(d)["findings"]]
    assert found == ([expected] if expected else [])


def test_unsupported_paas_type_warns():
    d = healthy()
    d["paas_resources"] = [{"id": P + "/Microsoft.Web/sites/app1", "name": "app1", "type": "Microsoft.Web/sites",
                            "publicNetworkAccess": "Enabled"}]
    r = exposure.analyze(d)
    assert r["findings"] == [] and any("unsupported type" in w for w in r["warnings"])


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = exposure.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) == 5
    assert "risky_mgmt_exposures" not in r["kpis"]
    d = healthy()
    del d["paas_resources"]
    r = exposure.analyze(d)
    assert len(r["evidence_gaps"]) == 1 and r["kpis"] == {"risky_mgmt_exposures": 0}
    assert exposure.analyze(healthy())["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    d["paas_resources"] = [storage()]
    d["paas_resources"][0]["id"] = OTHER + "/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st1"
    r = exposure.analyze(d)
    assert r["findings"] == []
    assert "1 paas_resources item(s) outside the managed scope were excluded." in r["warnings"]
    d["managed_scopes"] = None
    assert by_prefix(exposure.analyze(d), "EXP-PAAS-OPEN:st1")


def _all_findings():
    d = with_rules([rule(SUBNET_NSG, "allow-all", 100, protocol="*", src="*", ports=("*",))])
    d["public_ips"] += [pip(rid=N + "/publicIPAddresses/pip-free", attached=None, sku="Basic")]
    d["app_gateways"] = [agw("Standard_v2")]
    d["paas_resources"] = [storage(), storage(action="Deny", rules=1, name="st2"),
                           {"id": P + "/Microsoft.KeyVault/vaults/kv1", "name": "kv1",
                            "type": "Microsoft.KeyVault/vaults", "properties": {"publicNetworkAccess": "Enabled"}},
                           {"id": P + "/Microsoft.Sql/servers/sql1", "name": "sql1", "type": "Microsoft.Sql/servers",
                            "publicNetworkAccess": "Enabled"}]
    findings = exposure.analyze(d)["findings"]
    d2 = healthy()
    d2["app_gateways"] = [agw("WAF_v2", wafc={"enabled": True, "firewallMode": "Detection"})]
    findings += exposure.analyze(d2)["findings"]
    return findings + exposure.analyze(load_json(EX / "internet-exposure-input.json"))["findings"]


def test_remediation_scripts_are_human_review_and_commented():
    findings = _all_findings()
    prefixes = {f["id"].split(":", 1)[0] for f in findings}
    assert prefixes == {"EXP-MGMT-EXPOSED", "EXP-PORT-EXPOSED", "EXP-PIP-UNATTACHED", "EXP-PIP-BASIC",
                        "EXP-APPGW-NO-WAF", "EXP-APPGW-WAF-DETECTION", "EXP-PAAS-OPEN", "EXP-PAAS-FIREWALLED",
                        "EXP-SQL-PUBLIC"}
    for f in findings:
        lines = f["remediation_script"].splitlines()
        assert lines[0] == "# Human review required. Read-only verification (the agent never runs writes):"
        for idx, line in enumerate(lines):
            if line.startswith("az "):
                assert not CHANGE_RE.match(line), line
                assert guard.classify_az_command(concrete(line))["decision"] in ("allow_read", "allow_diagnostic"), line
            if line.startswith("# az ") and CHANGE_RE.match(line[2:]):
                assert "# Change (review before running):" in lines[:idx]
        assert f["citations"] and all(c.startswith("https://learn.microsoft.com/") for c in f["citations"])
        assert f["skill"] == "netops-exposure-scan"


def test_findings_sorted_and_ids_stable():
    r = exposure.analyze(load_json(EX / "internet-exposure-input.json"))
    order = ("critical", "high", "medium", "low", "info")
    keys = [(order.index(f["severity"]), f["resource_id"].casefold(), f["id"]) for f in r["findings"]]
    assert keys == sorted(keys)
    assert len(set(ids(r))) == len(ids(r))


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        exposure.analyze([])
    with pytest.raises(ValueError):
        exposure.analyze({"public_ips": {}})


def test_result_renders_through_adapter():
    r = exposure.analyze(load_json(EX / "internet-exposure-input.json"))
    model = models.build_exposure_scan_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "EXP-MGMT-EXPOSED" in html
    with pytest.raises(ValueError):
        models.build_nsg_firewall_audit_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert exposure.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-exposure-scan"


@pytest.mark.parametrize("command", STEPS_COMMANDS)
def test_steps_commands_are_read_only(command):
    assert guard.classify_az_command(concrete(command))["decision"] in ("allow_read", "allow_diagnostic")


def test_steps_commands_match_skill_md():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    steps = text.split("## Steps", 1)[1].split("## Evaluation model", 1)[0]
    listed = [" ".join(c.split()) for c in re.findall(r"`(az [^`]+)`", steps)]
    assert sorted(listed) == sorted(" ".join(c.split()) for c in STEPS_COMMANDS)
    assert text.rstrip().endswith(END)
