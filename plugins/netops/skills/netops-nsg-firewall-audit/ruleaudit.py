"""NetOps NSG and Azure Firewall rule audit — pure, offline, deterministic.

Audits network security group rules (and, when collected, Azure Firewall policy rule
collection groups) from raw read-only Azure responses that the agent already collected
(RunAzCliReadCommands / execute_kusto_query). Stdlib only: JSON in, JSON out, no I/O, no
clock, no network. Never executes or emits Azure writes; `remediation_script` values are
read-only verification commands or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "nsgs": [<ARM networkSecurityGroups object>],              # az network nsg list
          # securityRules[] / defaultSecurityRules[] with priority, direction, access, protocol,
          # sourceAddressPrefix(es), destinationAddressPrefix(es), sourcePortRange(s),
          # destinationPortRange(s), source/destinationApplicationSecurityGroups[];
          # subnets[] / networkInterfaces[] (associations)
      "firewall_rule_collection_groups": [<ARM ruleCollectionGroups object>],
          # az network firewall policy rule-collection-group list -g <rg> --policy-name <p>
      "rule_hits": [{"nsg_id": "<NSG ARM id or name>", "rule": "<rule name>", "hits": 0}],
          # per-rule flow counts over `rule_hits_window` from Traffic Analytics (NTANetAnalytics
          # AclGroup / AclRule). A rule is reported unused ONLY when an explicit entry has hits 0.
      "rule_hits_window": "30d",
      "thresholds": {"broad_port_count": 1024}
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py).
"""

from __future__ import annotations

import ipaddress
import json
import sys

SKILL = "netops-nsg-firewall-audit"

DOCS = {
    "nsg_overview": "https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview",
    "nsg_how": "https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works",
    "nsg_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/network-security-groups/get",
    "nsg_cli": "https://learn.microsoft.com/cli/azure/network/nsg",
    "nsg_rule_cli": "https://learn.microsoft.com/cli/azure/network/nsg/rule",
    "service_tags": "https://learn.microsoft.com/azure/virtual-network/service-tags-overview",
    "jit": "https://learn.microsoft.com/azure/defender-for-cloud/just-in-time-access-usage",
    "net_best": "https://learn.microsoft.com/azure/security/fundamentals/network-best-practices",
    "vpn_faq": "https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-vpn-faq",
    "ta_schema": "https://learn.microsoft.com/azure/network-watcher/traffic-analytics-schema",
    "nta_table": "https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntanetanalytics",
    "afw_rcg_rest": "https://learn.microsoft.com/rest/api/firewall/firewall-policy-rule-collection-groups/get",
    "afw_rcg_cli": "https://learn.microsoft.com/cli/azure/network/firewall/policy/rule-collection-group",
    "afw_rule_cli": "https://learn.microsoft.com/cli/azure/network/firewall/policy/rule-collection-group/collection/rule",
}

DEFAULT_THRESHOLDS = {"broad_port_count": 1024}
# Ports Defender for Cloud recommends protecting with just-in-time access (SSH, RDP, WinRM).
MGMT_PORTS = {22: "SSH", 3389: "RDP", 5985: "WinRM", 5986: "WinRM"}
# IKE (UDP 500) and IPsec NAT traversal (UDP 4500).
IKE_PORTS = (500, 4500)
ANY_TOKENS = {"*", "any"}
INTERNET_TOKENS = {"*", "any", "internet", "0.0.0.0/0", "::/0"}
FULL = ((0, 65535),)
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


# --- helpers ------------------------------------------------------------------------

def _text(value):
    return "" if value is None else str(value).strip()


def _norm_id(value):
    return _text(value).rstrip("/").casefold()


def _props(obj):
    props = obj.get("properties") if isinstance(obj, dict) else None
    if isinstance(props, dict):
        return props
    return obj if isinstance(obj, dict) else {}


def _ref(value):
    return _text(value.get("id")) if isinstance(value, dict) else _text(value)


def _name(resource_id, fallback=""):
    rid = _text(resource_id).rstrip("/")
    return rid.rsplit("/", 1)[-1] if rid else fallback


def _rg(resource_id):
    parts = _text(resource_id).split("/")
    lowered = [p.casefold() for p in parts]
    if "resourcegroups" in lowered:
        idx = lowered.index("resourcegroups")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "<resource-group>"


def _segment_after(resource_id, segment):
    parts = _text(resource_id).split("/")
    lowered = [p.casefold() for p in parts]
    if segment in lowered:
        idx = lowered.index(segment)
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_text(value))
    except ValueError:
        return None


def _in_scope(resource_id, managed):
    if managed is None:
        return True
    norm = _norm_id(resource_id)
    if not norm:
        return False
    return any(norm == m or norm.startswith(m + "/") for m in managed)


def _finding(fid, severity, resource_id, title, evidence, recommendation, script, citations):
    return {
        "id": fid,
        "skill": SKILL,
        "severity": severity,
        "resource_id": resource_id,
        "title": title,
        "evidence": evidence,
        "recommendation": recommendation,
        "remediation_script": script,
        "citations": sorted(set(citations)),
    }


def _human(lines):
    return "# Human review required. Read-only verification (the agent never runs writes):\n" + "\n".join(lines)


def _change(lines):
    return ["# Change (review before running):"] + ["# " + ln for ln in lines]


# --- rule model ---------------------------------------------------------------------

def _list(single, many):
    values = []
    if _text(single):
        values.append(_text(single))
    for v in many or []:
        if _text(v):
            values.append(_text(v))
    return values


def _ports(values):
    """Port strings -> merged [(lo, hi)]; '*' or nothing -> full range. None when unparsable."""

    if not values or any(v.casefold() in ANY_TOKENS for v in values):
        return list(FULL)
    ranges = []
    for v in values:
        lo, _, hi = v.partition("-")
        try:
            a, b = int(lo), int(hi or lo)
        except ValueError:
            return None
        ranges.append((min(a, b), max(a, b)))
    return _merge(ranges)


def _merge(ranges):
    merged = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _port_count(ranges):
    return sum(hi - lo + 1 for lo, hi in ranges)


def _covers_port(ranges, port):
    return any(lo <= port <= hi for lo, hi in ranges)


def _fmt_ports(ranges):
    if list(ranges) == list(FULL):
        return "*"
    return ",".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in ranges)


def _addresses(single, many, asgs):
    tokens = [v.casefold() for v in _list(single, many)]
    for asg in asgs or []:
        rid = _ref(asg)
        if rid:
            tokens.append("asg:" + _norm_id(rid))
    return tokens or ["*"]


def _rule(raw, default=False):
    p = _props(raw)
    name = _text(raw.get("name")) or _text(p.get("name"))
    priority = _num(p.get("priority"))
    return {
        "name": name,
        "id": _text(raw.get("id")),
        "default": default,
        "priority": int(priority) if priority is not None else 65535,
        "direction": _text(p.get("direction")).casefold() or "inbound",
        "access": _text(p.get("access")).casefold() or "allow",
        "protocol": _text(p.get("protocol")).casefold() or "*",
        "src": _addresses(p.get("sourceAddressPrefix"), p.get("sourceAddressPrefixes"),
                          p.get("sourceApplicationSecurityGroups")),
        "dst": _addresses(p.get("destinationAddressPrefix"), p.get("destinationAddressPrefixes"),
                          p.get("destinationApplicationSecurityGroups")),
        "sports": _ports(_list(p.get("sourcePortRange"), p.get("sourcePortRanges"))),
        "dports": _ports(_list(p.get("destinationPortRange"), p.get("destinationPortRanges"))),
    }


def _net(token):
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def _addr_covers(outer, inner):
    """Conservative: True only when every inner token is provably inside some outer token."""

    if any(t in ANY_TOKENS for t in outer):
        return True
    for tok in inner:
        if tok in ANY_TOKENS:
            return False
        if tok in outer:
            continue
        net = _net(tok)
        if net is None:
            return False
        if not any((o := _net(t)) is not None and o.version == net.version and net.subnet_of(o)
                   for t in outer):
            return False
    return True


def _ports_cover(outer, inner):
    if outer is None or inner is None:
        return False
    return all(any(olo <= lo and hi <= ohi for olo, ohi in outer) for lo, hi in inner)


def _covers(a, b):
    """True when rule `a` matches every packet rule `b` matches (same direction assumed)."""

    if a["protocol"] != "*" and a["protocol"] != b["protocol"]:
        return False
    return (_addr_covers(a["src"], b["src"]) and _addr_covers(a["dst"], b["dst"])
            and _ports_cover(a["sports"], b["sports"]) and _ports_cover(a["dports"], b["dports"]))


def _is_any_any(rule):
    return (rule["protocol"] == "*" and any(t in ANY_TOKENS for t in rule["src"])
            and any(t in ANY_TOKENS for t in rule["dst"])
            and rule["sports"] == list(FULL) and rule["dports"] == list(FULL))


def _from_internet(rule):
    return any(t in INTERNET_TOKENS for t in rule["src"])


def _describe(rule):
    return {"name": rule["name"], "priority": rule["priority"], "direction": rule["direction"].title(),
            "access": rule["access"].title(), "protocol": "*" if rule["protocol"] == "*" else rule["protocol"].title(),
            "source": rule["src"], "destination": rule["dst"],
            "destinationPorts": _fmt_ports(rule["dports"]) if rule["dports"] is not None else "<unparsed>"}


# --- NSG analysis -------------------------------------------------------------------

def _shadow_map(rules):
    """rule name -> first higher-priority rule (same direction) that fully covers it."""

    result = {}
    ordered = sorted(rules, key=lambda r: (r["priority"], r["name"]))
    for i, b in enumerate(ordered):
        if b["dports"] is None or b["sports"] is None:
            continue
        for a in ordered[:i]:
            if a["direction"] == b["direction"] and a["priority"] < b["priority"] and _covers(a, b):
                result[b["name"]] = a
                break
    return result


def _nsg_script(rid, rule=None):
    rg, nsg = _rg(rid), _name(rid)
    lines = [f"az network nsg rule list -g {rg} --nsg-name {nsg} --include-default -o table"]
    if rule:
        lines.append(f"az network nsg rule show -g {rg} --nsg-name {nsg} -n {rule} -o json")
    return lines


def _analyze_nsg(nsg, thresholds, hits, findings, counters):
    rid = _text(nsg.get("id"))
    p = _props(nsg)
    nsg_name = _text(nsg.get("name")) or _name(rid)
    rg = _rg(rid)
    custom = [_rule(r) for r in (p.get("securityRules") or []) if isinstance(r, dict)]
    counters["nsgs"] += 1
    counters["custom_rules"] += len(custom)

    subnets = [s for s in (p.get("subnets") or []) if _ref(s)]
    nics = [n for n in (p.get("networkInterfaces") or []) if _ref(n)]
    if not subnets and not nics:
        findings.append(_finding(
            f"NSG-UNASSOCIATED:{nsg_name}", "low", rid,
            f"NSG {nsg_name} is not associated with any subnet or network interface",
            {"subnets": 0, "networkInterfaces": 0, "customRules": len(custom)},
            "An unassociated NSG filters nothing. Associate it where intended or remove it after "
            "confirming no deployment references it.",
            _human([f"az network nsg show -g {rg} -n {nsg_name} --query \"{{subnets:subnets,nics:networkInterfaces}}\""]
                   + _change([f"az network nsg delete -g {rg} -n {nsg_name}"])),
            [DOCS["nsg_overview"], DOCS["nsg_cli"]]))

    shadow = _shadow_map(custom)
    deny_all_victims = {}
    for b in sorted(custom, key=lambda r: (r["priority"], r["name"])):
        a = shadow.get(b["name"])
        if a is None:
            continue
        if a["access"] == "deny" and b["access"] == "allow" and _is_any_any(a):
            deny_all_victims.setdefault(a["name"], (a, []))[1].append(b)
            continue
        opposite = a["access"] != b["access"]
        counters["shadowed"] += 1
        findings.append(_finding(
            f"NSG-{'SHADOWED' if opposite else 'REDUNDANT'}:{nsg_name}:{b['name']}",
            "medium" if opposite else "low", rid,
            (f"NSG {nsg_name}: {b['access'].title()} rule {b['name']} ({b['priority']}) never matches; "
             f"{a['access'].title()} rule {a['name']} ({a['priority']}) is evaluated first and covers it")
            if opposite else
            f"NSG {nsg_name}: rule {b['name']} ({b['priority']}) is redundant with {a['name']} ({a['priority']})",
            {"shadowed": _describe(b), "shadowedBy": _describe(a)},
            ("NSG rules are processed in priority order and processing stops at the first match. "
             "Re-order or narrow the higher-priority rule if the lower one is still intended; otherwise "
             "remove the dead rule.") if opposite else
            "The lower-priority rule adds nothing; remove it to simplify the rule base.",
            _human(_nsg_script(rid, b["name"])
                   + _change([f"az network nsg rule delete -g {rg} --nsg-name {nsg_name} -n {b['name']}"])),
            [DOCS["nsg_overview"], DOCS["nsg_how"], DOCS["nsg_rule_cli"]]))

    for deny_name, (a, victims) in sorted(deny_all_victims.items()):
        counters["shadowed"] += len(victims)
        inbound = a["direction"] == "inbound"
        findings.append(_finding(
            f"NSG-DENY-ALL-SHADOWS:{nsg_name}:{deny_name}", "critical" if inbound else "high", rid,
            f"NSG {nsg_name}: {a['direction']} deny-all rule {deny_name} (priority {a['priority']}) "
            f"shadows {len(victims)} allow rule(s)",
            {"denyRule": _describe(a), "shadowedAllowRules": [_describe(v) for v in victims],
             "associatedSubnets": sorted(_name(_ref(s)) for s in subnets),
             "associatedNics": sorted(_name(_ref(n)) for n in nics)},
            f"Rule {deny_name} matches all {a['direction']} traffic before any allow rule, so every "
            "workload behind this NSG is cut off. If this was not an intentional lockdown, remove it "
            "or move it below the allow rules (higher priority number).",
            _human(_nsg_script(rid, deny_name)
                   + _change([f"az network nsg rule delete -g {rg} --nsg-name {nsg_name} -n {deny_name}"])),
            [DOCS["nsg_overview"], DOCS["nsg_how"], DOCS["nsg_rule_cli"]]))

    # A fully covered rule never matches; the covering rule is assessed on its own.
    dead = set(shadow)
    broad_limit = int(thresholds["broad_port_count"])
    for r in sorted(custom, key=lambda r: (r["priority"], r["name"])):
        if r["dports"] is None:
            continue
        live = r["name"] not in dead
        if r["access"] == "allow" and r["direction"] == "inbound" and _from_internet(r) and live:
            if r["protocol"] in ("*", "tcp"):
                ports = sorted(p for p in MGMT_PORTS if _covers_port(r["dports"], p))
                if ports:
                    counters["mgmt"] += 1
                    findings.append(_finding(
                        f"NSG-MGMT-FROM-INTERNET:{nsg_name}:{r['name']}", "critical", rid,
                        f"NSG {nsg_name}: rule {r['name']} allows management ports "
                        f"{', '.join(f'{p}/{MGMT_PORTS[p]}' for p in ports)} from the Internet",
                        {"rule": _describe(r), "managementPorts": ports},
                        "Do not expose SSH/RDP/WinRM to the Internet. Use Azure Bastion or just-in-time "
                        "VM access and restrict the source to known management prefixes.",
                        _human(_nsg_script(rid, r["name"])
                               + _change([f"az network nsg rule update -g {rg} --nsg-name {nsg_name} "
                                          f"-n {r['name']} --access Deny"])),
                        [DOCS["jit"], DOCS["net_best"], DOCS["nsg_rule_cli"]]))
            count = _port_count(r["dports"])
            if count >= broad_limit:
                counters["broad"] += 1
                findings.append(_finding(
                    f"NSG-BROAD-ALLOW:{nsg_name}:{r['name']}", "high", rid,
                    f"NSG {nsg_name}: rule {r['name']} allows {_fmt_ports(r['dports'])} "
                    f"({count} ports) inbound from {', '.join(r['src'])}",
                    {"rule": _describe(r), "allowedPortCount": count, "broadPortThreshold": broad_limit},
                    "Restrict the source to specific prefixes / service tags and the destination ports "
                    "to the application ports actually required.",
                    _human(_nsg_script(rid, r["name"])
                           + _change([f"az network nsg rule update -g {rg} --nsg-name {nsg_name} "
                                      f"-n {r['name']} --source-address-prefixes <trusted-prefix> "
                                      "--destination-port-ranges <app-port>"])),
                    [DOCS["nsg_overview"], DOCS["service_tags"], DOCS["nsg_rule_cli"]]))
        if (r["access"] == "deny" and r["protocol"] in ("*", "udp") and r["dports"] != list(FULL)
                and (r["name"] not in dead or shadow[r["name"]]["access"] == "deny")):
            blocked = [p for p in IKE_PORTS if _covers_port(r["dports"], p)]
            if blocked:
                findings.append(_finding(
                    f"NSG-IKE-BLOCKED:{nsg_name}:{r['name']}", "high", rid,
                    f"NSG {nsg_name}: rule {r['name']} blocks IKE/IPsec (UDP 500/4500) {r['direction']}",
                    {"rule": _describe(r), "blockedPorts": blocked,
                     "associatedSubnets": sorted(_name(_ref(s)) for s in subnets)},
                    "Site-to-site IPsec needs UDP 500 (IKE) and UDP 4500 (NAT traversal) between the VPN "
                    "peers; the tunnel drops at the next rekey. Remove the deny or scope it away from "
                    "the VPN peer addresses, then confirm with netops-hybrid-health.",
                    _human(_nsg_script(rid, r["name"])
                           + _change([f"az network nsg rule delete -g {rg} --nsg-name {nsg_name} -n {r['name']}"])),
                    [DOCS["vpn_faq"], DOCS["nsg_overview"], DOCS["nsg_rule_cli"]]))

    if hits is not None:
        for r in sorted(custom, key=lambda r: (r["priority"], r["name"])):
            count = hits.get((_norm_id(rid), r["name"].casefold()))
            if count is None:
                count = hits.get((nsg_name.casefold(), r["name"].casefold()))
            if count is None or count > 0:
                continue
            findings.append(_finding(
                f"NSG-UNUSED-RULE:{nsg_name}:{r['name']}", "low", rid,
                f"NSG {nsg_name}: rule {r['name']} had 0 flow hits in the observed window",
                {"rule": _describe(r), "hits": 0, "window": counters["window"]},
                "Flow-log evidence shows no matching flows. Confirm with the owner (rules may protect "
                "rare or seasonal traffic) before removing it.",
                _human(_nsg_script(rid, r["name"])
                       + ["# KQL: NTANetAnalytics | where SubType == \"FlowLog\" | where AclRule == "
                          f"\"{r['name']}\" | summarize count()"]
                       + _change([f"az network nsg rule delete -g {rg} --nsg-name {nsg_name} -n {r['name']}"])),
                [DOCS["ta_schema"], DOCS["nta_table"], DOCS["nsg_rule_cli"]]))


# --- Azure Firewall policy ----------------------------------------------------------

def _analyze_rcgs(rcgs, findings, counters):
    for rcg in sorted(rcgs, key=lambda g: _norm_id(g.get("id"))):
        rid = _text(rcg.get("id"))
        p = _props(rcg)
        policy = _segment_after(rid, "firewallpolicies") or "<policy>"
        group = _text(rcg.get("name")) or _name(rid)
        for coll in p.get("ruleCollections") or []:
            if not isinstance(coll, dict):
                continue
            if _text(coll.get("ruleCollectionType")) != "FirewallPolicyFilterRuleCollection":
                continue
            action = _text((coll.get("action") or {}).get("type")).casefold()
            if action != "allow":
                continue
            cname = _text(coll.get("name"))
            for rule in coll.get("rules") or []:
                if not isinstance(rule, dict):
                    continue
                counters["fw_rules"] += 1
                rtype = _text(rule.get("ruleType"))
                src_any = "*" in [_text(s) for s in rule.get("sourceAddresses") or []]
                if rtype == "NetworkRule":
                    dst_any = "*" in [_text(s) for s in rule.get("destinationAddresses") or []]
                    port_any = "*" in [_text(s) for s in rule.get("destinationPorts") or []]
                    broad = src_any and (dst_any or port_any)
                elif rtype == "ApplicationRule":
                    broad = src_any and "*" in [_text(s) for s in rule.get("targetFqdns") or []]
                else:
                    broad = False
                if not broad:
                    continue
                rname = _text(rule.get("name"))
                counters["broad"] += 1
                findings.append(_finding(
                    f"AFW-BROAD-ALLOW:{policy}:{group}:{cname}:{rname}", "high", rid,
                    f"Azure Firewall policy {policy}: {rtype} {rname} in {cname} allows source * to a "
                    "wildcard destination",
                    {"policy": policy, "ruleCollectionGroup": group, "ruleCollection": cname,
                     "collectionPriority": coll.get("priority"), "ruleType": rtype,
                     "sourceAddresses": rule.get("sourceAddresses") or [],
                     "destinationAddresses": rule.get("destinationAddresses") or [],
                     "destinationPorts": rule.get("destinationPorts") or [],
                     "targetFqdns": rule.get("targetFqdns") or [],
                     "ipProtocols": rule.get("ipProtocols") or []},
                    "Replace wildcard sources/destinations/ports with IP groups, specific prefixes, FQDNs "
                    "and the ports the workload needs.",
                    _human([f"az network firewall policy rule-collection-group show -g {_rg(rid)} "
                            f"--policy-name {policy} -n {group} -o json"]
                           + _change([f"az network firewall policy rule-collection-group collection rule update "
                                      f"-g {_rg(rid)} --policy-name {policy} --rcg-name {group} "
                                      f"--collection-name {cname} -n {rname} --source-addresses <trusted-prefix>"])),
                    [DOCS["afw_rcg_rest"], DOCS["afw_rcg_cli"], DOCS["afw_rule_cli"]]))


# --- entry point --------------------------------------------------------------------

def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update({k: v for k, v in (data.get("thresholds") or {}).items() if k in DEFAULT_THRESHOLDS})
    managed = data.get("managed_scopes")
    if managed is not None:
        managed = [_norm_id(s) for s in managed if _norm_id(s)]

    findings, gaps, warnings = [], [], []
    dropped = {}

    def items(key, id_getter):
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        kept = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if _in_scope(id_getter(item), managed):
                kept.append(item)
            else:
                dropped[key] = dropped.get(key, 0) + 1
        return kept

    nsgs = items("nsgs", lambda n: n.get("id"))
    rcgs = items("firewall_rule_collection_groups", lambda g: g.get("id"))
    raw_hits = data.get("rule_hits")
    if raw_hits is not None and not isinstance(raw_hits, list):
        raise ValueError("rule_hits must be an array")

    hits = None
    if raw_hits is not None:
        hits = {}
        for h in raw_hits:
            if not isinstance(h, dict):
                continue
            count = _num(h.get("hits"))
            if count is None:
                continue
            key = (_norm_id(h.get("nsg_id")), _text(h.get("rule")).casefold())
            hits[key] = hits.get(key, 0) + count

    counters = {"nsgs": 0, "custom_rules": 0, "broad": 0, "shadowed": 0, "mgmt": 0, "fw_rules": 0,
                "window": _text(data.get("rule_hits_window")) or "unspecified"}

    if nsgs is None:
        gaps.append("nsgs not collected (az network nsg list); NSG rule audit skipped.")
    else:
        for nsg in sorted(nsgs, key=lambda n: _norm_id(n.get("id"))):
            _analyze_nsg(nsg, thresholds, hits, findings, counters)
    if rcgs is None:
        gaps.append("firewall_rule_collection_groups not collected (az network firewall policy "
                    "rule-collection-group list -g <rg> --policy-name <policy>); Azure Firewall policy "
                    "rules not audited.")
    else:
        _analyze_rcgs(rcgs, findings, counters)
    if raw_hits is None:
        gaps.append("rule_hits not collected (Traffic Analytics NTANetAnalytics AclGroup/AclRule flow "
                    "counts); unused-rule analysis skipped; no rule is reported as unused without evidence.")

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"]), f["resource_id"].casefold(), f["id"]))
    kpis = {}
    if nsgs is not None or rcgs is not None:
        kpis["broad_rules"] = counters["broad"]
    metric_rows = [
        {"label": "NSGs audited", "value": str(counters["nsgs"]),
         "detail": f"{counters['custom_rules']} custom rules", "tone": "neutral"},
        {"label": "Overly broad allow rules", "value": str(counters["broad"]),
         "detail": f"Internet/any source with >= {thresholds['broad_port_count']} ports, or Azure Firewall wildcard allow",
         "tone": "good" if counters["broad"] == 0 else ("warning" if counters["broad"] <= 5 else "critical")},
        {"label": "Management ports from Internet", "value": str(counters["mgmt"]),
         "detail": "22 / 3389 / 5985 / 5986 allowed from Internet or *",
         "tone": "good" if counters["mgmt"] == 0 else "critical"},
        {"label": "Shadowed / redundant rules", "value": str(counters["shadowed"]),
         "detail": "fully covered by a higher-priority rule", "tone": "good" if counters["shadowed"] == 0 else "warning"},
        {"label": "Azure Firewall allow rules audited", "value": str(counters["fw_rules"]),
         "detail": "filter rule collections (Allow)", "tone": "neutral"},
    ]
    return {
        "skill": SKILL,
        "findings": findings,
        "evidence_gaps": gaps,
        "metrics": metric_rows,
        "kpis": kpis,
        "partial": bool(gaps),
        "warnings": warnings,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] not in ("-",):
        with open(argv[0], encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.load(sys.stdin)
    json.dump(analyze(data), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
