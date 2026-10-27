"""netops-nsg-firewall-audit engine: findings, evidence gaps, scope filtering, determinism."""

import copy
import json
import re

import pytest

from conftest import SKILLS, load_json, load_skill_module

ruleaudit = load_skill_module("netops-nsg-firewall-audit", "ruleaudit.py")
models = load_skill_module("netops-report-renderer", "models.py")
render = load_skill_module("netops-report-renderer", "render.py")
guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

SKILL_DIR = SKILLS / "netops-nsg-firewall-audit"
EX = SKILL_DIR / "examples"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
OTHER = "/subscriptions/00000000-0000-0000-0000-000000000009"
NSG = SUB + "/resourceGroups/rg-netops-spoke/providers/Microsoft.Network/networkSecurityGroups/nsg-app"
SUBNET = SUB + "/resourceGroups/rg-netops-spoke/providers/Microsoft.Network/virtualNetworks/vnet/subnets/snet-app"
POLICY = SUB + "/resourceGroups/rg-netops-hub/providers/Microsoft.Network/firewallPolicies/afwp-hub"

# Every az command listed in SKILL.md "Steps" (placeholders kept as written).
STEPS_COMMANDS = (
    "az network nsg list -o json",
    "az network nsg rule list -g <rg> --nsg-name <nsg> --include-default -o json",
    "az network firewall policy list -o json",
    "az network firewall policy rule-collection-group list -g <rg> --policy-name <policy> -o json",
)

CHANGE_RE = re.compile(r"^az\s+.*\b(create|update|delete|set|add|remove)\b")
END = "Analysis only — verify against vendor documentation before applying."


def concrete(command):
    return re.sub(r"<[^>]+>", "x", command)


def rule(name, priority, access="Allow", protocol="Tcp", src="10.0.0.0/8", dst="*", ports=("443",),
         direction="Inbound", srcs=None):
    props = {"priority": priority, "direction": direction, "access": access, "protocol": protocol,
             "sourcePortRange": "*", "destinationAddressPrefix": dst}
    if srcs:
        props["sourceAddressPrefixes"] = list(srcs)
    else:
        props["sourceAddressPrefix"] = src
    if len(ports) == 1:
        props["destinationPortRange"] = ports[0]
    else:
        props["destinationPortRanges"] = list(ports)
    return {"id": f"{NSG}/securityRules/{name}", "name": name, "properties": props}


def nsg(rules, rid=NSG, subnets=(SUBNET,), nics=()):
    return {"id": rid, "name": rid.rsplit("/", 1)[-1],
            "properties": {"securityRules": rules, "subnets": [{"id": s} for s in subnets],
                           "networkInterfaces": [{"id": n} for n in nics]}}


def healthy():
    return {
        "managed_scopes": [SUB],
        "nsgs": [nsg([rule("allow-https-corp", 200), rule("allow-ssh-corp", 210, ports=("22",))])],
        "firewall_rule_collection_groups": [],
        "rule_hits": [],
    }


def rcg(rules, action="Allow", ctype="FirewallPolicyFilterRuleCollection"):
    return {"id": POLICY + "/ruleCollectionGroups/rcg-app", "name": "rcg-app",
            "properties": {"priority": 200, "ruleCollections": [
                {"name": "coll-app", "priority": 100, "ruleCollectionType": ctype,
                 "action": {"type": action}, "rules": rules}]}}


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_prefix(result, prefix):
    return [f for f in result["findings"] if f["id"].startswith(prefix)]


def test_healthy_has_no_findings():
    r = ruleaudit.analyze(healthy())
    assert r["skill"] == "netops-nsg-firewall-audit"
    assert r["findings"] == [] and r["evidence_gaps"] == [] and r["partial"] is False
    assert r["kpis"] == {"broad_rules": 0}
    for m in r["metrics"]:
        assert m["tone"] in ("neutral", "good", "warning", "critical")


@pytest.mark.parametrize("name", ["sc04-deny-all", "sc02-ike-block"])
def test_example_output_is_deterministic(name):
    data = load_json(EX / f"{name}-input.json")
    expected = load_json(EX / f"{name}-output.json")
    assert ruleaudit.analyze(copy.deepcopy(data)) == expected
    assert json.dumps(ruleaudit.analyze(data), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_sc04_deny_all_shadows_allows_is_critical():
    r = ruleaudit.analyze(load_json(EX / "sc04-deny-all-input.json"))
    top = r["findings"][0]
    assert top["id"] == "NSG-DENY-ALL-SHADOWS:nsg-netops-app:sc04-deny-inbound"
    assert top["severity"] == "critical"
    assert "shadows 1 allow rule" in top["title"]
    # victims are grouped under the deny-all finding, not reported separately
    assert not by_prefix(r, "NSG-SHADOWED:")
    assert r["partial"] is True and any("rule_hits" in g for g in r["evidence_gaps"])


def test_sc02_ike_block_is_high_and_shadows_ipsec_allow():
    r = ruleaudit.analyze(load_json(EX / "sc02-ike-block-input.json"))
    ike = by_prefix(r, "NSG-IKE-BLOCKED:")
    assert [f["id"] for f in ike] == ["NSG-IKE-BLOCKED:nsg-netops-onprem-outside:sc02-block-ike"]
    assert ike[0]["severity"] == "high" and "UDP 500/4500" in ike[0]["title"]
    shadowed = by_prefix(r, "NSG-SHADOWED:")
    assert [f["id"] for f in shadowed] == ["NSG-SHADOWED:nsg-netops-onprem-outside:allow-ipsec-inbound"]
    assert shadowed[0]["severity"] == "medium"


def test_deny_all_outbound_is_high():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-all-out", 100, "Deny", "*", "*", "*", ("*",), "Outbound"),
                      rule("allow-https-out", 200, dst="Internet", direction="Outbound")])]
    f = by_prefix(ruleaudit.analyze(d), "NSG-DENY-ALL-SHADOWS:")
    assert len(f) == 1 and f[0]["severity"] == "high"


def test_deny_all_without_victims_is_not_reported():
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-https-corp", 100), rule("deny-all", 4000, "Deny", "*", "*", "*", ("*",))])]
    assert not by_prefix(ruleaudit.analyze(d), "NSG-DENY-ALL-SHADOWS:")


@pytest.mark.parametrize("src", ["*", "Internet", "0.0.0.0/0"])
@pytest.mark.parametrize("port", ["22", "3389", "5985", "5986"])
def test_management_port_from_internet_is_critical(src, port):
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-mgmt", 300, src=src, ports=(port,))])]
    r = ruleaudit.analyze(d)
    f = by_prefix(r, "NSG-MGMT-FROM-INTERNET:")
    assert [x["id"] for x in f] == ["NSG-MGMT-FROM-INTERNET:nsg-app:allow-mgmt"]
    assert f[0]["severity"] == "critical"


def test_management_port_from_trusted_prefix_or_udp_is_not_flagged():
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-ssh-udp", 300, protocol="Udp", src="*", ports=("22",)),
                      rule("allow-rdp-corp", 310, src="203.0.113.0/24", ports=("3389",))])]
    assert not by_prefix(ruleaudit.analyze(d), "NSG-MGMT-FROM-INTERNET:")


def test_broad_allow_counts_into_kpi():
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-any", 300, protocol="*", src="Internet", ports=("*",)),
                      rule("allow-high", 310, src="*", ports=("1024-65535",)),
                      rule("allow-small-range", 320, src="*", ports=("8000-8010",))])]
    r = ruleaudit.analyze(d)
    broad = by_prefix(r, "NSG-BROAD-ALLOW:")
    assert sorted(f["id"] for f in broad) == ["NSG-BROAD-ALLOW:nsg-app:allow-any", "NSG-BROAD-ALLOW:nsg-app:allow-high"]
    assert all(f["severity"] == "high" for f in broad)
    assert r["kpis"]["broad_rules"] == 2
    # allow-any also opens management ports from the Internet
    assert by_prefix(r, "NSG-MGMT-FROM-INTERNET:nsg-app:allow-any")


def test_broad_port_threshold_is_configurable():
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-small-range", 320, src="*", ports=("8000-8010",))])]
    d["thresholds"] = {"broad_port_count": 10}
    assert ruleaudit.analyze(d)["kpis"]["broad_rules"] == 1


def test_shadowed_and_redundant_rules():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-corp-web", 100, "Deny", src="10.0.0.0/8", ports=("80", "443")),
                      rule("allow-corp-https", 200, src="10.1.0.0/16", ports=("443",)),
                      rule("allow-corp-all", 300, protocol="*", src="10.0.0.0/8", ports=("*",)),
                      rule("allow-subnet-ssh", 400, src="10.1.2.0/24", ports=("22",))])]
    r = ruleaudit.analyze(d)
    assert [f["id"] for f in by_prefix(r, "NSG-SHADOWED:")] == ["NSG-SHADOWED:nsg-app:allow-corp-https"]
    assert by_prefix(r, "NSG-SHADOWED:")[0]["severity"] == "medium"
    red = by_prefix(r, "NSG-REDUNDANT:")
    assert [f["id"] for f in red] == ["NSG-REDUNDANT:nsg-app:allow-subnet-ssh"]
    assert red[0]["severity"] == "low"


def test_shadow_check_is_conservative():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-tag", 100, "Deny", src="VirtualNetwork", ports=("443",)),
                      rule("allow-prefix", 200, src="10.1.0.0/16", ports=("443",)),
                      rule("deny-udp", 300, "Deny", protocol="Udp", src="*", ports=("53",)),
                      rule("allow-tcp-dns", 400, src="10.1.0.0/16", ports=("53",)),
                      rule("deny-other-dir", 500, "Deny", src="*", ports=("8443",), direction="Outbound"),
                      rule("allow-8443", 600, src="10.1.0.0/16", ports=("8443",))])]
    r = ruleaudit.analyze(d)
    assert not by_prefix(r, "NSG-SHADOWED:") and not by_prefix(r, "NSG-REDUNDANT:")


def test_shadowed_rules_are_not_reported_as_exposures():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-ssh", 100, "Deny", src="*", ports=("22",)),
                      rule("allow-ssh-any", 200, src="*", ports=("22",))])]
    r = ruleaudit.analyze(d)
    assert by_prefix(r, "NSG-SHADOWED:nsg-app:allow-ssh-any")
    assert not by_prefix(r, "NSG-MGMT-FROM-INTERNET:")


def test_ike_deny_outbound_and_any_protocol():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-natt-out", 100, "Deny", protocol="*", src="*", ports=("4500",),
                           direction="Outbound"),
                      rule("deny-web", 110, "Deny", protocol="Tcp", src="*", ports=("500",))])]
    f = by_prefix(ruleaudit.analyze(d), "NSG-IKE-BLOCKED:")
    assert [x["id"] for x in f] == ["NSG-IKE-BLOCKED:nsg-app:deny-natt-out"]


def test_unassociated_nsg_is_low():
    d = healthy()
    d["nsgs"] = [nsg([], subnets=())]
    f = by_prefix(ruleaudit.analyze(d), "NSG-UNASSOCIATED:")
    assert [x["id"] for x in f] == ["NSG-UNASSOCIATED:nsg-app"] and f[0]["severity"] == "low"
    d["nsgs"] = [nsg([], subnets=(), nics=(SUB + "/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/n1",))]
    assert not by_prefix(ruleaudit.analyze(d), "NSG-UNASSOCIATED:")


def test_unused_rules_need_explicit_zero_hits():
    d = healthy()
    d["rule_hits"] = [{"nsg_id": NSG, "rule": "allow-https-corp", "hits": 1200},
                      {"nsg_id": "nsg-app", "rule": "allow-ssh-corp", "hits": 0}]
    d["rule_hits_window"] = "30d"
    r = ruleaudit.analyze(d)
    f = by_prefix(r, "NSG-UNUSED-RULE:")
    assert [x["id"] for x in f] == ["NSG-UNUSED-RULE:nsg-app:allow-ssh-corp"]
    assert f[0]["severity"] == "low" and f[0]["evidence"]["window"] == "30d"
    # a rule absent from rule_hits is never called unused
    d["rule_hits"] = [{"nsg_id": NSG, "rule": "allow-https-corp", "hits": 5}]
    assert not by_prefix(ruleaudit.analyze(d), "NSG-UNUSED-RULE:")
    # without rule_hits: evidence gap, no unused findings
    del d["rule_hits"]
    r = ruleaudit.analyze(d)
    assert not by_prefix(r, "NSG-UNUSED-RULE:")
    assert r["partial"] is True and any("rule_hits" in g for g in r["evidence_gaps"])


def test_azure_firewall_wildcard_allows():
    d = healthy()
    d["firewall_rule_collection_groups"] = [rcg([
        {"ruleType": "NetworkRule", "name": "any-any", "sourceAddresses": ["*"], "destinationAddresses": ["*"],
         "destinationPorts": ["443"], "ipProtocols": ["TCP"]},
        {"ruleType": "NetworkRule", "name": "any-ports", "sourceAddresses": ["*"],
         "destinationAddresses": ["10.1.0.0/16"], "destinationPorts": ["*"], "ipProtocols": ["Any"]},
        {"ruleType": "NetworkRule", "name": "scoped", "sourceAddresses": ["10.1.0.0/16"],
         "destinationAddresses": ["*"], "destinationPorts": ["*"], "ipProtocols": ["Any"]},
        {"ruleType": "ApplicationRule", "name": "any-fqdn", "sourceAddresses": ["*"], "targetFqdns": ["*"],
         "protocols": [{"protocolType": "Https", "port": 443}]},
        {"ruleType": "ApplicationRule", "name": "one-fqdn", "sourceAddresses": ["*"],
         "targetFqdns": ["www.microsoft.com"]}])]
    r = ruleaudit.analyze(d)
    afw = by_prefix(r, "AFW-BROAD-ALLOW:")
    assert sorted(f["id"] for f in afw) == [
        "AFW-BROAD-ALLOW:afwp-hub:rcg-app:coll-app:any-any",
        "AFW-BROAD-ALLOW:afwp-hub:rcg-app:coll-app:any-fqdn",
        "AFW-BROAD-ALLOW:afwp-hub:rcg-app:coll-app:any-ports"]
    assert all(f["severity"] == "high" for f in afw)
    assert r["kpis"]["broad_rules"] == 3


@pytest.mark.parametrize("action,ctype", [("Deny", "FirewallPolicyFilterRuleCollection"),
                                          ("DNAT", "FirewallPolicyNatRuleCollection")])
def test_azure_firewall_deny_and_nat_collections_ignored(action, ctype):
    d = healthy()
    d["firewall_rule_collection_groups"] = [rcg([
        {"ruleType": "NetworkRule", "name": "any-any", "sourceAddresses": ["*"], "destinationAddresses": ["*"],
         "destinationPorts": ["*"]}], action=action, ctype=ctype)]
    assert not by_prefix(ruleaudit.analyze(d), "AFW-")


def test_absent_inputs_are_gaps_empty_lists_are_not():
    r = ruleaudit.analyze({"managed_scopes": [SUB]})
    assert r["partial"] is True and len(r["evidence_gaps"]) == 3
    assert "broad_rules" not in r["kpis"]
    assert ruleaudit.analyze(healthy())["evidence_gaps"] == []


def test_out_of_scope_items_dropped_with_warning():
    d = healthy()
    d["nsgs"].append(nsg([rule("allow-any", 100, protocol="*", src="*", ports=("*",))],
                         rid=OTHER + "/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/nsg-x"))
    r = ruleaudit.analyze(d)
    assert r["findings"] == []
    assert "1 nsgs item(s) outside the managed scope were excluded." in r["warnings"]
    d["managed_scopes"] = None
    assert by_prefix(ruleaudit.analyze(d), "NSG-BROAD-ALLOW:nsg-x:")


def _all_findings():
    d = healthy()
    d["nsgs"] = [nsg([rule("deny-ssh", 100, "Deny", src="*", ports=("22",)),
                      rule("allow-ssh-any", 200, src="*", ports=("22",)),
                      rule("allow-any", 300, protocol="*", src="Internet", ports=("*",)),
                      rule("allow-ssh-corp", 400, src="10.0.0.0/8", ports=("22",))], subnets=())]
    d["rule_hits"] = [{"nsg_id": NSG, "rule": "allow-ssh-corp", "hits": 0}]
    d["firewall_rule_collection_groups"] = [rcg([
        {"ruleType": "NetworkRule", "name": "any-any", "sourceAddresses": ["*"], "destinationAddresses": ["*"],
         "destinationPorts": ["*"]}])]
    findings = ruleaudit.analyze(d)["findings"]
    for name in ("sc04-deny-all", "sc02-ike-block"):
        findings += ruleaudit.analyze(load_json(EX / f"{name}-input.json"))["findings"]
    return findings


def test_remediation_scripts_are_human_review_and_commented():
    findings = _all_findings()
    prefixes = {f["id"].split(":", 1)[0] for f in findings}
    assert {"NSG-SHADOWED", "NSG-MGMT-FROM-INTERNET", "NSG-BROAD-ALLOW", "NSG-UNASSOCIATED", "NSG-UNUSED-RULE",
            "AFW-BROAD-ALLOW", "NSG-DENY-ALL-SHADOWS", "NSG-IKE-BLOCKED"} <= prefixes
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
        assert f["skill"] == "netops-nsg-firewall-audit"


def test_findings_sorted_and_ids_stable():
    d = healthy()
    d["nsgs"] = [nsg([rule("allow-any", 300, protocol="*", src="Internet", ports=("*",)),
                      rule("allow-ssh-corp", 400, src="10.0.0.0/8", ports=("22",))], subnets=())]
    r = ruleaudit.analyze(d)
    order = ("critical", "high", "medium", "low", "info")
    keys = [(order.index(f["severity"]), f["resource_id"].casefold(), f["id"]) for f in r["findings"]]
    assert keys == sorted(keys)
    assert len(set(ids(r))) == len(ids(r))


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        ruleaudit.analyze([])
    with pytest.raises(ValueError):
        ruleaudit.analyze({"nsgs": {}})
    with pytest.raises(ValueError):
        ruleaudit.analyze({"rule_hits": "x"})


def test_result_renders_through_adapter():
    r = ruleaudit.analyze(load_json(EX / "sc04-deny-all-input.json"))
    model = models.build_nsg_firewall_audit_model(r, refreshed_at="2025-01-14T08:00:00Z")
    html = render.render_report(model)
    assert "NSG-DENY-ALL-SHADOWS" in html
    with pytest.raises(ValueError):
        models.build_exposure_scan_model(r, refreshed_at="2025-01-14T08:00:00Z")


def test_cli_main(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(healthy()), encoding="utf-8")
    assert ruleaudit.main([str(p)]) in (0, None)
    assert json.loads(capsys.readouterr().out)["skill"] == "netops-nsg-firewall-audit"


@pytest.mark.parametrize("command", STEPS_COMMANDS)
def test_steps_commands_are_read_only(command):
    assert guard.classify_az_command(concrete(command))["decision"] in ("allow_read", "allow_diagnostic")


def test_steps_commands_match_skill_md():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    steps = text.split("## Steps", 1)[1].split("## Interpretation", 1)[0]
    listed = [" ".join(c.split()) for c in re.findall(r"`(az [^`]+)`", steps)]
    assert sorted(listed) == sorted(" ".join(c.split()) for c in STEPS_COMMANDS)
    assert text.rstrip().endswith(END)
