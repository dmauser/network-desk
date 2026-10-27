"""NetOps Internet exposure scan — pure, offline, deterministic.

Finds what is reachable from the Internet in the managed scope: management and other ports on
public-IP network interfaces (effective subnet NSG + NIC NSG evaluation), unattached and Basic
SKU public IPs, public Application Gateways without WAF, and PaaS resources whose public network
access is enabled. Works on raw read-only Azure responses the agent already collected
(RunAzCliReadCommands). Stdlib only: JSON in, JSON out, no I/O, no clock, no network. Never
executes or emits Azure writes; `remediation_script` values are read-only verification commands
or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "public_ips":   [<publicIPAddresses object>],   # az network public-ip list
                       # ipAddress, ipConfiguration.id, natGateway.id, sku.name (Basic/Standard)
      "nics":         [<networkInterfaces object>],   # az network nic list
                       # ipConfigurations[].publicIPAddress.id / privateIPAddress / subnet.id /
                       # applicationSecurityGroups[]; networkSecurityGroup.id
      "nsgs":         [<networkSecurityGroups object>],   # az network nsg list
                       # securityRules[], defaultSecurityRules[], subnets[] (subnet association)
      "app_gateways": [<applicationGateways object>],    # az network application-gateway list
                       # sku.tier, firewallPolicy.id, webApplicationFirewallConfiguration,
                       # frontendIPConfigurations[].publicIPAddress.id
      "paas_resources": [<resource object with "type">],
                       # az storage account list / az keyvault show / az sql server list
                       # Microsoft.Storage/storageAccounts: publicNetworkAccess, networkRuleSet|networkAcls
                       # Microsoft.KeyVault/vaults: publicNetworkAccess, networkAcls
                       # Microsoft.Sql/servers: publicNetworkAccess
      "bastions":     [<bastionHosts object>]            # optional: az network bastion list
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py).
"""

from __future__ import annotations

import ipaddress
import json
import sys

SKILL = "netops-exposure-scan"

DOCS = {
    "nsg_overview": "https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview",
    "nsg_how": "https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works",
    "nsg_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/network-security-groups/get",
    "nsg_rule_cli": "https://learn.microsoft.com/cli/azure/network/nsg/rule",
    "nic_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get",
    "nic_cli": "https://learn.microsoft.com/cli/azure/network/nic",
    "pip": "https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-addresses",
    "pip_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/public-ip-addresses/get",
    "pip_cli": "https://learn.microsoft.com/cli/azure/network/public-ip",
    "pip_basic": "https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-basic-upgrade-guidance",
    "jit": "https://learn.microsoft.com/azure/defender-for-cloud/just-in-time-access-usage",
    "net_best": "https://learn.microsoft.com/azure/security/fundamentals/network-best-practices",
    "agw_rest": "https://learn.microsoft.com/rest/api/application-gateway/application-gateways/get",
    "agw_cli": "https://learn.microsoft.com/cli/azure/network/application-gateway",
    "agw_waf_cli": "https://learn.microsoft.com/cli/azure/network/application-gateway/waf-policy",
    "storage_rest": "https://learn.microsoft.com/rest/api/storagerp/storage-accounts/get-properties",
    "storage_cli": "https://learn.microsoft.com/cli/azure/storage/account",
    "kv_rest": "https://learn.microsoft.com/rest/api/keyvault/keyvault/vaults/get",
    "kv_cli": "https://learn.microsoft.com/cli/azure/keyvault",
    "sql_rest": "https://learn.microsoft.com/rest/api/sql/servers/get",
    "sql_cli": "https://learn.microsoft.com/cli/azure/sql/server",
    "sql_fw_cli": "https://learn.microsoft.com/cli/azure/sql/server/firewall-rule",
    "bastion_cli": "https://learn.microsoft.com/cli/azure/network/bastion",
}

# Ports Defender for Cloud recommends protecting with just-in-time access (SSH, RDP, WinRM).
MGMT_PORTS = {22: "SSH", 3389: "RDP", 5985: "WinRM", 5986: "WinRM"}
INTERNET_TOKENS = {"*", "any", "internet", "0.0.0.0/0", "::/0"}
ANY_DEST_TOKENS = {"*", "any", "virtualnetwork", "0.0.0.0/0"}
WAF_TIERS = {"waf", "waf_v2", "basic_waf_v2"}
STORAGE, KEYVAULT, SQL = "microsoft.storage/storageaccounts", "microsoft.keyvault/vaults", "microsoft.sql/servers"
FULL = [(0, 65535)]
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


def _parent_nic(ipconfig_id):
    """'.../networkInterfaces/<nic>/ipConfigurations/<cfg>' -> NIC id (normalized), else ''."""

    parts = _text(ipconfig_id).split("/")
    lowered = [p.casefold() for p in parts]
    if "networkinterfaces" in lowered:
        idx = lowered.index("networkinterfaces")
        return _norm_id("/".join(parts[:idx + 2]))
    return ""


def _attached_type(ipconfig_id):
    parts = _text(ipconfig_id).split("/")
    lowered = [p.casefold() for p in parts]
    if "providers" in lowered:
        idx = lowered.index("providers")
        if idx + 2 < len(parts):
            return parts[idx + 2]
    return ""


# --- port intervals -----------------------------------------------------------------

def _list(single, many):
    values = [_text(single)] if _text(single) else []
    return values + [_text(v) for v in many or [] if _text(v)]


def _ports(values):
    if not values or any(v.casefold() in ("*", "any") for v in values):
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


def _intersect(a, b):
    out = []
    for alo, ahi in a:
        for blo, bhi in b:
            lo, hi = max(alo, blo), min(ahi, bhi)
            if lo <= hi:
                out.append((lo, hi))
    return _merge(out)


def _subtract_points(ranges, points):
    out = []
    for lo, hi in ranges:
        start = lo
        for p in sorted(x for x in points if lo <= x <= hi):
            if start <= p - 1:
                out.append((start, p - 1))
            start = p + 1
        if start <= hi:
            out.append((start, hi))
    return out


def _covers_port(ranges, port):
    return any(lo <= port <= hi for lo, hi in ranges)


def _fmt_ports(ranges):
    if ranges == FULL:
        return "*"
    return ",".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in ranges)


# --- NSG evaluation for Internet-sourced inbound traffic ----------------------------

def _rules(nsg):
    p = _props(nsg)
    out = []
    for raw in list(p.get("securityRules") or []) + list(p.get("defaultSecurityRules") or []):
        if not isinstance(raw, dict):
            continue
        rp = _props(raw)
        if _text(rp.get("direction")).casefold() != "inbound":
            continue
        prio = _num(rp.get("priority"))
        src = [v.casefold() for v in _list(rp.get("sourceAddressPrefix"), rp.get("sourceAddressPrefixes"))]
        dst = [v.casefold() for v in _list(rp.get("destinationAddressPrefix"), rp.get("destinationAddressPrefixes"))]
        dst += ["asg:" + _norm_id(_ref(a)) for a in rp.get("destinationApplicationSecurityGroups") or [] if _ref(a)]
        out.append({
            "name": _text(raw.get("name")),
            "priority": int(prio) if prio is not None else 65535,
            "access": _text(rp.get("access")).casefold(),
            "protocol": _text(rp.get("protocol")).casefold() or "*",
            "src": src or ["*"],
            "dst": dst or ["*"],
            "sports": _ports(_list(rp.get("sourcePortRange"), rp.get("sourcePortRanges"))),
            "dports": _ports(_list(rp.get("destinationPortRange"), rp.get("destinationPortRanges"))),
        })
    # Platform default DenyAllInBound (priority 65500) applies when defaults were not collected.
    return sorted(out, key=lambda r: (r["priority"], r["name"]))


def _dest_matches(tokens, ip, asgs):
    for tok in tokens:
        if tok in ANY_DEST_TOKENS or tok in asgs:
            return True
        if ip is not None:
            try:
                if ip in ipaddress.ip_network(tok, strict=False):
                    return True
            except ValueError:
                continue
    return False


def _matches(rule, proto, ip, asgs):
    if rule["dports"] is None or rule["sports"] is None:
        return False
    if rule["protocol"] not in ("*", proto):
        return False
    if not any(t in INTERNET_TOKENS for t in rule["src"]):
        return False
    # A deny only blocks all Internet clients when it is not limited to specific source ports.
    if rule["access"] == "deny" and rule["sports"] != FULL:
        return False
    return _dest_matches(rule["dst"], ip, asgs)


def _allowed(nsg, proto, ip, asgs):
    """-> (allowed port intervals, {port-range-start: allowing rule}) for Internet inbound."""

    rules = [r for r in _rules(nsg) if _matches(r, proto, ip, asgs)]
    bounds = {0, 65536}
    for r in rules:
        for lo, hi in r["dports"]:
            bounds.update((lo, hi + 1))
    edges = sorted(bounds)
    allowed, by = [], {}
    for lo, nxt in zip(edges, edges[1:]):
        for r in rules:
            if _covers_port(r["dports"], lo):
                if r["access"] == "allow":
                    allowed.append((lo, nxt - 1))
                    by[lo] = r["name"]
                break
    return _merge(allowed), by


# --- analysis -----------------------------------------------------------------------

def _analyze_nics(nics, nsg_index, subnet_nsg, pip_index, bastions, findings, gaps, counters):
    for nic in sorted(nics, key=lambda n: _norm_id(n.get("id"))):
        nic_id = _text(nic.get("id"))
        p = _props(nic)
        nic_name = _text(nic.get("name")) or _name(nic_id)
        nic_nsg_id = _norm_id(_ref(p.get("networkSecurityGroup")))
        for cfg in p.get("ipConfigurations") or []:
            if not isinstance(cfg, dict):
                continue
            cp = _props(cfg)
            pip_id = _norm_id(_ref(cp.get("publicIPAddress")))
            if not pip_id:
                continue
            counters["public_nics"] += 1
            pip = pip_index.get(pip_id, {})
            pp = _props(pip)
            sku = _text((pip.get("sku") or pp.get("sku") or {}).get("name"))
            address = _text(pp.get("ipAddress")) or "<unknown>"
            try:
                ip = ipaddress.ip_address(_text(cp.get("privateIPAddress")))
            except ValueError:
                ip = None
            asgs = {"asg:" + _norm_id(_ref(a)) for a in cp.get("applicationSecurityGroups") or [] if _ref(a)}
            levels = []
            sub_nsg = subnet_nsg.get(_norm_id(_ref(cp.get("subnet"))))
            if sub_nsg:
                levels.append(("subnet", sub_nsg))
            if nic_nsg_id:
                if nic_nsg_id not in nsg_index:
                    gaps.append(f"NSG {_name(nic_nsg_id)} on NIC {nic_name} not collected (or outside the "
                                "managed scope); its exposure was not evaluated.")
                    continue
                levels.append(("nic", nsg_index[nic_nsg_id]))
            if not levels and sku.casefold() != "basic":
                continue
            exposure, allowed_by = {}, {}
            for proto in ("tcp", "udp"):
                ranges = list(FULL)
                by = {}
                if not levels:
                    by["*"] = ["no NSG (Basic SKU public IP is open by default)"]
                for level, nsg in levels:
                    allowed, rule_by = _allowed(nsg, proto, ip, asgs)
                    ranges = _intersect(ranges, allowed)
                    by[f"{level}:{_text(nsg.get('name')) or _name(nsg.get('id'))}"] = sorted(set(rule_by.values()))
                if ranges:
                    exposure[proto] = ranges
                    allowed_by[proto] = by
            if not exposure:
                continue
            path = [f"{lvl}:{_text(n.get('name')) or _name(n.get('id'))}" for lvl, n in levels] or ["none"]
            bastion_hint = (f" Azure Bastion is available ({', '.join(bastions)})." if bastions else "")
            tcp = exposure.get("tcp", [])
            mgmt = [port for port in sorted(MGMT_PORTS) if _covers_port(tcp, port)]
            for port in mgmt:
                counters["mgmt"] += 1
                findings.append(_finding(
                    f"EXP-MGMT-EXPOSED:{nic_name}:{port}", "critical", nic_id,
                    f"{MGMT_PORTS[port]} (TCP {port}) on {nic_name} is reachable from the Internet via {address}",
                    {"publicIp": address, "publicIpSku": sku or "<unknown>", "privateIp": str(ip) if ip else "",
                     "port": port, "nsgPath": path, "allowedBy": allowed_by.get("tcp", {})},
                    "Close management ports to the Internet: use Azure Bastion or just-in-time VM access and "
                    "restrict any remaining rule to trusted source prefixes." + bastion_hint,
                    _human([f"az network nic list-effective-nsg -g {_rg(nic_id)} -n {nic_name} -o json"]
                           + [f"az network nsg rule list -g {_rg(n.get('id'))} --nsg-name "
                              f"{_text(n.get('name')) or _name(n.get('id'))} --include-default -o table"
                              for _lvl, n in levels]
                           + _change(["az network nsg rule update -g <nsg-rg> --nsg-name <nsg> -n <allowing-rule> "
                                      "--access Deny"])),
                    [DOCS["jit"], DOCS["net_best"], DOCS["nsg_how"], DOCS["nic_cli"], DOCS["nsg_rule_cli"]]))
            other = {proto: _subtract_points(r, mgmt if proto == "tcp" else []) for proto, r in exposure.items()}
            other = {proto: r for proto, r in other.items() if r}
            if other:
                counters["other"] += 1
                findings.append(_finding(
                    f"EXP-PORT-EXPOSED:{nic_name}", "medium", nic_id,
                    f"{nic_name} exposes " + "; ".join(f"{proto.upper()} {_fmt_ports(r)}" for proto, r in sorted(other.items()))
                    + f" to the Internet via {address}",
                    {"publicIp": address, "publicIpSku": sku or "<unknown>", "privateIp": str(ip) if ip else "",
                     "openPorts": {proto.upper(): _fmt_ports(r) for proto, r in sorted(other.items())},
                     "nsgPath": path, "allowedBy": {k.upper(): v for k, v in sorted(allowed_by.items())}},
                    "Confirm each open port is an intended public service; prefer publishing through a load "
                    "balancer or Application Gateway with WAF instead of an instance-level public IP.",
                    _human([f"az network nic list-effective-nsg -g {_rg(nic_id)} -n {nic_name} -o json"]),
                    [DOCS["nsg_how"], DOCS["pip"], DOCS["nic_cli"]]))


def _analyze_pips(pips, findings, counters):
    for pip in sorted(pips, key=lambda x: _norm_id(x.get("id"))):
        rid = _text(pip.get("id"))
        p = _props(pip)
        name = _text(pip.get("name")) or _name(rid)
        sku = _text((pip.get("sku") or p.get("sku") or {}).get("name"))
        cfg = _ref(p.get("ipConfiguration"))
        nat = _ref(p.get("natGateway"))
        counters["pips"] += 1
        if not cfg and not nat:
            findings.append(_finding(
                f"EXP-PIP-UNATTACHED:{name}", "low", rid,
                f"Public IP {name} ({_text(p.get('ipAddress')) or 'unassigned'}) is not attached to any resource",
                {"ipAddress": _text(p.get("ipAddress")), "sku": sku},
                "Unattached public IPs add attack surface if re-attached by mistake and incur cost; delete "
                "it if no workload owns it.",
                _human([f"az network public-ip show -g {_rg(rid)} -n {name} -o json"]
                       + _change([f"az network public-ip delete -g {_rg(rid)} -n {name}"])),
                [DOCS["pip"], DOCS["pip_cli"]]))
        elif cfg and not _parent_nic(cfg):
            counters["other_attached"] += 1
        if sku.casefold() == "basic":
            findings.append(_finding(
                f"EXP-PIP-BASIC:{name}", "low", rid,
                f"Public IP {name} uses the retired Basic SKU (open by default)",
                {"sku": sku, "ipAddress": _text(p.get("ipAddress")), "attachedTo": _attached_type(cfg)},
                "Basic SKU public IPs were retired on September 30, 2025 and are open to inbound traffic "
                "by default. Upgrade to Standard SKU (secure by default) and add an NSG.",
                _human([f"az network public-ip show -g {_rg(rid)} -n {name} --query \"{{sku:sku,ip:ipAddress}}\""]),
                [DOCS["pip_basic"], DOCS["pip"]]))


def _analyze_agws(agws, findings, counters):
    for agw in sorted(agws, key=lambda x: _norm_id(x.get("id"))):
        rid = _text(agw.get("id"))
        p = _props(agw)
        name = _text(agw.get("name")) or _name(rid)
        public = any(_ref(_props(f).get("publicIPAddress")) for f in p.get("frontendIPConfigurations") or []
                     if isinstance(f, dict))
        if not public:
            continue
        counters["public_agws"] += 1
        tier = _text((p.get("sku") or agw.get("sku") or {}).get("tier"))
        policy = _ref(p.get("firewallPolicy"))
        wafc = p.get("webApplicationFirewallConfiguration") or {}
        enabled = bool(policy) or wafc.get("enabled") is True
        script = _human([f"az network application-gateway show -g {_rg(rid)} -n {name} --query "
                         "\"{sku:sku,firewallPolicy:firewallPolicy,waf:webApplicationFirewallConfiguration}\"",
                         f"az network application-gateway waf-policy list -g {_rg(rid)} -o table"])
        if tier.casefold() not in WAF_TIERS or not enabled:
            findings.append(_finding(
                f"EXP-APPGW-NO-WAF:{name}", "high", rid,
                f"Public Application Gateway {name} has no Web Application Firewall (tier {tier or '<unknown>'})",
                {"skuTier": tier, "firewallPolicy": policy, "wafConfigEnabled": wafc.get("enabled")},
                "Internet-facing web apps should be protected by WAF: move to the WAF_v2 tier and associate "
                "a WAF policy in Prevention mode.",
                script, [DOCS["agw_rest"], DOCS["agw_cli"], DOCS["agw_waf_cli"]]))
        elif not policy and _text(wafc.get("firewallMode")).casefold() == "detection":
            findings.append(_finding(
                f"EXP-APPGW-WAF-DETECTION:{name}", "medium", rid,
                f"Application Gateway {name} WAF is in Detection mode (logs only, does not block)",
                {"skuTier": tier, "firewallMode": wafc.get("firewallMode")},
                "After tuning exclusions, switch WAF to Prevention mode so attacks are blocked.",
                script, [DOCS["agw_rest"], DOCS["agw_cli"]]))


def _analyze_paas(resources, findings, counters, warnings):
    unsupported = 0
    for res in sorted(resources, key=lambda x: _norm_id(x.get("id"))):
        rid = _text(res.get("id"))
        rtype = _text(res.get("type")).casefold()
        p = _props(res)
        name = _text(res.get("name")) or _name(rid)
        rg = _rg(rid)
        if rtype not in (STORAGE, KEYVAULT, SQL):
            unsupported += 1
            continue
        counters["paas"] += 1
        pna = _text(p.get("publicNetworkAccess") or res.get("publicNetworkAccess"))
        if pna.casefold() in ("disabled", "securedbyperimeter"):
            continue
        if rtype == SQL:
            if pna.casefold() != "enabled":
                continue
            counters["paas_public"] += 1
            findings.append(_finding(
                f"EXP-SQL-PUBLIC:{name}", "low", rid,
                f"SQL server {name} has public network access Enabled",
                {"type": res.get("type"), "publicNetworkAccess": pna},
                "Access through the public endpoint is governed by the server firewall rules; review them "
                "and prefer private endpoints with public network access Disabled.",
                _human([f"az sql server show -g {rg} -n {name} --query publicNetworkAccess",
                        f"az sql server firewall-rule list -g {rg} --server {name} -o table"]
                       + _change([f"az sql server update -g {rg} -n {name} --enable-public-network false"])),
                [DOCS["sql_rest"], DOCS["sql_cli"], DOCS["sql_fw_cli"]]))
            continue
        acl = p.get("networkRuleSet") or p.get("networkAcls") or res.get("networkRuleSet") or {}
        action = _text(acl.get("defaultAction") if isinstance(acl, dict) else "")
        rules = (len(acl.get("ipRules") or []) + len(acl.get("virtualNetworkRules") or [])) if isinstance(acl, dict) else 0
        if rtype == STORAGE:
            show = f"az storage account show -g {rg} -n {name} --query \"{{pna:publicNetworkAccess,acl:networkRuleSet}}\""
            change = f"az storage account update -g {rg} -n {name} --public-network-access Disabled"
            cites = [DOCS["storage_rest"], DOCS["storage_cli"]]
        else:
            show = f"az keyvault show -g {rg} -n {name} --query \"{{pna:properties.publicNetworkAccess,acl:properties.networkAcls}}\""
            change = f"az keyvault update -g {rg} -n {name} --public-network-access Disabled"
            cites = [DOCS["kv_rest"], DOCS["kv_cli"]]
        evidence = {"type": res.get("type"), "publicNetworkAccess": pna or "<not reported>",
                    "defaultAction": action or "<not reported>", "ipAndVnetRules": rules}
        counters["paas_public"] += 1
        if action.casefold() == "deny":
            findings.append(_finding(
                f"EXP-PAAS-FIREWALLED:{name}", "low" if rules else "info", rid,
                f"{name}: public endpoint enabled but default action Deny"
                + (f" with {rules} IP/VNet rule(s)" if rules else ""),
                evidence,
                "Public access is limited to the listed IP/VNet rules. If clients use private endpoints only, "
                "disable public network access.",
                _human([show] + _change([change])), cites))
            continue
        findings.append(_finding(
            f"EXP-PAAS-OPEN:{name}", "high" if action.casefold() == "allow" else "medium", rid,
            f"{name}: public network access enabled with default action {action or 'not reported'}",
            evidence,
            "The service accepts traffic from any Internet address (subject to authentication). Set the "
            "network default action to Deny with explicit IP/VNet rules, or disable public network access "
            "and use private endpoints.",
            _human([show] + _change([change])), cites))
    if unsupported:
        warnings.append(f"{unsupported} paas_resources item(s) of unsupported type were skipped "
                        "(supported: storage accounts, key vaults, SQL servers).")


def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    managed = data.get("managed_scopes")
    if managed is not None:
        managed = [_norm_id(s) for s in managed if _norm_id(s)]

    findings, gaps, warnings = [], [], []
    dropped = {}

    def items(key):
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        kept = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if _in_scope(item.get("id"), managed):
                kept.append(item)
            else:
                dropped[key] = dropped.get(key, 0) + 1
        return kept

    pips = items("public_ips")
    nics = items("nics")
    nsgs = items("nsgs")
    agws = items("app_gateways")
    paas = items("paas_resources")
    bastions = items("bastions")

    counters = {"pips": 0, "public_nics": 0, "mgmt": 0, "other": 0, "other_attached": 0,
                "public_agws": 0, "paas": 0, "paas_public": 0}

    if pips is None:
        gaps.append("public_ips not collected (az network public-ip list); unattached / Basic public IP "
                    "checks skipped.")
    else:
        _analyze_pips(pips, findings, counters)

    if nics is None:
        gaps.append("nics not collected (az network nic list); public-IP NIC exposure not evaluated.")
    if nsgs is None:
        gaps.append("nsgs not collected (az network nsg list); effective NSG exposure not evaluated.")
    if nics is not None and nsgs is not None:
        nsg_index = {_norm_id(n.get("id")): n for n in nsgs}
        subnet_nsg = {}
        for n in sorted(nsgs, key=lambda n: _norm_id(n.get("id"))):
            for s in _props(n).get("subnets") or []:
                subnet_nsg.setdefault(_norm_id(_ref(s)), n)
        pip_index = {_norm_id(x.get("id")): x for x in pips or []}
        bastion_names = sorted(_text(b.get("name")) or _name(b.get("id")) for b in bastions or [])
        _analyze_nics(nics, nsg_index, subnet_nsg, pip_index, bastion_names, findings, gaps, counters)

    if agws is None:
        gaps.append("app_gateways not collected (az network application-gateway list); WAF coverage not checked.")
    else:
        _analyze_agws(agws, findings, counters)
    if paas is None:
        gaps.append("paas_resources not collected (az storage account list, az keyvault show, "
                    "az sql server list); PaaS public network access not checked.")
    else:
        _analyze_paas(paas, findings, counters, warnings)

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"]), f["resource_id"].casefold(), f["id"]))
    kpis = {}
    if nics is not None and nsgs is not None:
        kpis["risky_mgmt_exposures"] = counters["mgmt"]
    metric_rows = [
        {"label": "Mgmt ports open to Internet", "value": str(counters["mgmt"]),
         "detail": "TCP 22 / 3389 / 5985 / 5986 on public-IP NICs (subnet + NIC NSG)",
         "tone": "good" if counters["mgmt"] == 0 else "critical"},
        {"label": "Public-IP NICs with other open ports", "value": str(counters["other"]),
         "detail": f"{counters['public_nics']} NIC IP configuration(s) with a public IP",
         "tone": "good" if counters["other"] == 0 else "warning"},
        {"label": "Public IPs", "value": str(counters["pips"]),
         "detail": f"{counters['other_attached']} on load balancers / gateways / other services (not port-evaluated)",
         "tone": "neutral"},
        {"label": "Public Application Gateways", "value": str(counters["public_agws"]),
         "detail": "frontend with a public IP", "tone": "neutral"},
        {"label": "PaaS with public access", "value": f"{counters['paas_public']}/{counters['paas']}",
         "detail": "storage, key vault, SQL server", "tone": "good" if counters["paas_public"] == 0 else "warning"},
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
