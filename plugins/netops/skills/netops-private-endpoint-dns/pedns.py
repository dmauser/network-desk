"""NetOps private endpoint + private DNS validation — pure, offline, deterministic.

Validates that every in-scope private endpoint (PE) is approved, has the right private DNS zone,
that the zone is linked to the VNets that resolve it, and that the A record matches the PE IP.
Stdlib only: JSON in, JSON out, no I/O, no clock, no network, never writes to Azure.

Input (every key optional; ABSENT = not collected -> evidence gap, EMPTY list = none found)::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,
      "private_endpoints": [<ARM privateEndpoints object>],       # az network private-endpoint list
      "dns_zone_groups": [{"private_endpoint_id": "...", "value": [<privateDnsZoneGroups object>]}],
                                   # az network private-endpoint dns-zone-group list --endpoint-name
      "private_dns_zones": [<ARM privateDnsZones object>],       # az network private-dns zone list
      "vnet_links": [<ARM virtualNetworkLinks object>],          # az network private-dns link vnet list
      "a_records": [<ARM privateDnsZones/A object>],             # az network private-dns record-set a list
      "resolver_vnets": ["<vnet id>"],     # VNets whose resolution uses Azure DNS (168.63.129.16),
                                           # e.g. the hub hosting DNS Private Resolver. Default: each
                                           # PE's own VNet.
      "resolution_checks": [{"fqdn": "...", "resolved_ips": ["10.1.2.4"], "from": "vm-x"}]
    }
"""

from __future__ import annotations

import ipaddress
import json
import sys

SKILL = "netops-private-endpoint-dns"

DOCS = {
    "pe_dns": "https://learn.microsoft.com/azure/private-link/private-endpoint-dns",
    "pe_pending": "https://learn.microsoft.com/troubleshoot/azure/private-link/troubleshoot-private-endpoint-pending-approval",
    "pe_overview": "https://learn.microsoft.com/azure/private-link/private-endpoint-overview",
    "dns_links": "https://learn.microsoft.com/azure/dns/private-dns-virtual-network-links",
    "dns_fallback": "https://learn.microsoft.com/azure/dns/private-dns-fallback",
    "nxdomain": "https://learn.microsoft.com/troubleshoot/azure/dns/troubleshoot-private-dns-zone-override-nxdomain",
    "zone_group": "https://learn.microsoft.com/rest/api/virtualnetwork/private-dns-zone-groups/get",
    "pe_dns_integration": "https://learn.microsoft.com/azure/private-link/private-endpoint-dns-integration",
}

# groupId (subresource) -> recommended private DNS zone(s), from private-endpoint-dns.
ZONES_BY_GROUP = {
    "blob": ("privatelink.blob.core.windows.net",),
    "blob_secondary": ("privatelink.blob.core.windows.net",),
    "file": ("privatelink.file.core.windows.net",),
    "queue": ("privatelink.queue.core.windows.net",),
    "table": ("privatelink.table.core.windows.net",),
    "dfs": ("privatelink.dfs.core.windows.net",),
    "web": ("privatelink.web.core.windows.net",),
    "sqlserver": ("privatelink.database.windows.net",),
    "vault": ("privatelink.vaultcore.azure.net",),
    "registry": ("privatelink.azurecr.io",),
    "sites": ("privatelink.azurewebsites.net",),
    "sql": ("privatelink.documents.azure.com",),
    "namespace": ("privatelink.servicebus.windows.net",),
    "account": ("privatelink.cognitiveservices.azure.com", "privatelink.openai.azure.com"),
    "searchservice": ("privatelink.search.windows.net",),
}

_LINK_READY = {"completed", "done"}
_SEV_ORDER = ("critical", "high", "medium", "low", "info")


# --- helpers ------------------------------------------------------------------------

def _text(value):
    return "" if value is None else str(value).strip()


def _norm(value):
    return _text(value).rstrip("/").casefold()


def _props(obj):
    props = obj.get("properties") if isinstance(obj, dict) else None
    if isinstance(props, dict):
        return props
    return obj if isinstance(obj, dict) else {}


def _ref(value):
    return _text(value.get("id")) if isinstance(value, dict) else _text(value)


def _name(resource_id):
    return _text(resource_id).rstrip("/").rsplit("/", 1)[-1]


def _rg(resource_id):
    parts = _text(resource_id).split("/")
    low = [p.casefold() for p in parts]
    if "resourcegroups" in low and low.index("resourcegroups") + 1 < len(parts):
        return parts[low.index("resourcegroups") + 1]
    return "<resource-group>"


def _vnet_of_subnet(subnet_id):
    sid = _text(subnet_id)
    idx = sid.casefold().find("/subnets/")
    return sid[:idx] if idx >= 0 else ""


def _zone_of_child(resource_id):
    """Zone id for .../privateDnsZones/<zone>/(A|virtualNetworkLinks)/<name>."""
    rid = _text(resource_id)
    idx = rid.casefold().find("/privatednszones/")
    if idx < 0:
        return ""
    rest = rid[idx + len("/privateDnsZones/"):]
    return rid[:idx + len("/privateDnsZones/")] + rest.split("/", 1)[0]


def _in_scope(resource_id, managed):
    if managed is None:
        return True
    norm = _norm(resource_id)
    return bool(norm) and any(norm == m or norm.startswith(m + "/") for m in managed)


def _is_public(ip):
    try:
        addr = ipaddress.ip_address(_text(ip))
    except ValueError:
        return False
    return addr.is_global


def _finding(fid, severity, resource_id, title, evidence, recommendation, script, citations):
    return {"id": fid, "skill": SKILL, "severity": severity, "resource_id": resource_id,
            "title": title, "evidence": evidence, "recommendation": recommendation,
            "remediation_script": script, "citations": sorted(set(citations))}


def _human(lines):
    return "# Human review required. Read-only verification (the agent never runs writes):\n" + "\n".join(lines)


def _connections(pe):
    p = _props(pe)
    rows = []
    for key, manual in (("privateLinkServiceConnections", False), ("manualPrivateLinkServiceConnections", True)):
        for conn in p.get(key) or []:
            cp = _props(conn)
            state = cp.get("privateLinkServiceConnectionState") or {}
            rows.append({"name": _text(conn.get("name")), "manual": manual,
                         "target": _text(cp.get("privateLinkServiceId")),
                         "group_ids": [_text(g) for g in cp.get("groupIds") or [] if _text(g)],
                         "status": _text(state.get("status")) or "Unknown",
                         "description": _text(state.get("description")),
                         "actions_required": _text(state.get("actionsRequired"))})
    return rows


def _expected_records(pe, zone_configs):
    """{(zone_name, record_name): set(ips)} from zone-group recordSets, else customDnsConfigs."""
    expected = {}
    for cfg in zone_configs:
        zone_name = _name(cfg["zone_id"]).casefold()
        for rs in cfg["record_sets"]:
            if _text(rs.get("recordType") or "A").upper() != "A":
                continue
            rec = _text(rs.get("recordSetName")).casefold()
            if rec:
                expected.setdefault((zone_name, rec), set()).update(_text(i) for i in rs.get("ipAddresses") or [])
    if expected:
        return expected, "zone-group recordSets"
    zones = sorted({_name(c["zone_id"]).casefold() for c in zone_configs})
    for dns in _props(pe).get("customDnsConfigs") or []:
        fqdn = _text(dns.get("fqdn")).casefold().rstrip(".")
        ips = {_text(i) for i in dns.get("ipAddresses") or []}
        for zone in zones:
            public = zone.removeprefix("privatelink.")
            if fqdn.endswith("." + public):
                expected.setdefault((zone, fqdn[: -len(public) - 1]), set()).update(ips)
    return expected, "customDnsConfigs"


# --- analysis -----------------------------------------------------------------------

def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    managed = data.get("managed_scopes")
    if managed is not None:
        managed = [_norm(s) for s in managed if _norm(s)]
    findings, gaps, warnings, dropped = [], [], [], {}

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

    pes = items("private_endpoints", lambda x: x.get("id"))
    zone_groups = items("dns_zone_groups", lambda x: x.get("private_endpoint_id"))
    zones = items("private_dns_zones", lambda x: x.get("id"))
    links = items("vnet_links", lambda x: x.get("id"))
    records = items("a_records", lambda x: x.get("id"))
    checks = data.get("resolution_checks")
    resolver_vnets = [_norm(v) for v in data.get("resolver_vnets") or [] if _norm(v)]

    if pes is None:
        gaps.append("private_endpoints not collected (az network private-endpoint list).")
        pes = []
    if zone_groups is None:
        gaps.append("dns_zone_groups not collected (az network private-endpoint dns-zone-group list); "
                    "zone mapping inferred from customDnsConfigs only.")
    if zones is None:
        gaps.append("private_dns_zones not collected (az network private-dns zone list).")
    if links is None:
        gaps.append("vnet_links not collected (az network private-dns link vnet list); link check skipped.")
    if records is None:
        gaps.append("a_records not collected (az network private-dns record-set a list); record check skipped.")

    zone_ids = {_norm(z.get("id")) for z in zones or []}
    zone_by_name = {}
    for z in zones or []:
        zone_by_name.setdefault(_text(z.get("name")).casefold(), []).append(_text(z.get("id")))
    links_by_zone = {}
    for link in links or []:
        links_by_zone.setdefault(_norm(_zone_of_child(link.get("id"))), []).append(link)
    records_by_zone = {}
    for rec in records or []:
        records_by_zone.setdefault(_norm(_zone_of_child(rec.get("id"))), {})[
            _text(rec.get("name")).casefold()] = rec
    groups_by_pe = {}
    for entry in zone_groups or []:
        groups_by_pe.setdefault(_norm(entry.get("private_endpoint_id")), []).extend(
            g for g in entry.get("value") or [] if isinstance(g, dict))

    pe_ips = set()
    healthy = 0
    reported_links = set()
    for pe in sorted(pes, key=lambda x: _norm(x.get("id"))):
        rid = _text(pe.get("id"))
        name = _text(pe.get("name")) or _name(rid)
        p = _props(pe)
        rg = _rg(rid)
        bad = False
        for dns in p.get("customDnsConfigs") or []:
            pe_ips.update(_text(i) for i in dns.get("ipAddresses") or [])

        conns = _connections(pe)
        group_ids = sorted({g.casefold() for c in conns for g in c["group_ids"]})
        for c in conns:
            if c["status"] == "Approved":
                continue
            sev = "high" if c["status"] == "Pending" else "critical"
            bad = True
            findings.append(_finding(
                f"PE-CONN-{c['status'].upper()}:{name}", sev, rid,
                f"Private endpoint {name} connection is {c['status']}",
                {"connection": c["name"], "status": c["status"], "target": _name(c["target"]),
                 "manual": c["manual"], "description": c["description"],
                 "actionsRequired": c["actions_required"]},
                "Pending: the target resource owner must approve the connection. Rejected/Disconnected: "
                "the connection carries no traffic; re-request approval or recreate the endpoint.",
                _human([f"az network private-endpoint show -g {rg} -n {name} --query "
                        "\"[privateLinkServiceConnections,manualPrivateLinkServiceConnections][].{name:name,"
                        "status:privateLinkServiceConnectionState.status}\" -o table"]),
                [DOCS["pe_pending"]]))

        zone_configs = []
        groups = groups_by_pe.get(_norm(rid), [])
        for group in groups:
            gp = _props(group)
            if _text(gp.get("provisioningState")) == "Failed":
                bad = True
                findings.append(_finding(
                    f"PE-ZONE-GROUP-FAILED:{name}", "high", rid,
                    f"DNS zone group {_text(group.get('name'))} on {name} is Failed",
                    {"provisioningState": "Failed"},
                    "The zone group did not register the A records. Inspect the zone group and the zone.",
                    _human([f"az network private-endpoint dns-zone-group list -g {rg} --endpoint-name {name}"]),
                    [DOCS["zone_group"]]))
            for cfg in gp.get("privateDnsZoneConfigs") or []:
                cp = _props(cfg)
                zone_configs.append({"zone_id": _text(cp.get("privateDnsZoneId")),
                                     "record_sets": [r for r in cp.get("recordSets") or [] if isinstance(r, dict)]})

        expected_zone_names = sorted({z for g in group_ids for z in ZONES_BY_GROUP.get(g, ())})
        if zone_groups is not None and not zone_configs:
            # No zone group: fall back to zones in inventory matching the expected names.
            for zname in expected_zone_names:
                for zid in zone_by_name.get(zname, []):
                    zone_configs.append({"zone_id": zid, "record_sets": []})
            sev = "high" if not zone_configs else "medium"
            bad = bad or sev == "high"
            findings.append(_finding(
                f"PE-NO-ZONE-GROUP:{name}", sev, rid,
                f"Private endpoint {name} has no private DNS zone group",
                {"groupIds": group_ids, "expected_zones": expected_zone_names,
                 "matching_zones_found": sorted(_name(c["zone_id"]) for c in zone_configs)},
                "Without a zone group, A records are not managed automatically and drift when the PE "
                "IP changes. Add a zone group for the recommended zone (human-run change).",
                _human([f"az network private-endpoint dns-zone-group list -g {rg} --endpoint-name {name}",
                        "# Change (review before running):",
                        f"# az network private-endpoint dns-zone-group create -g {rg} --endpoint-name {name} "
                        f"-n default --private-dns-zone <zone-id> --zone-name {expected_zone_names[0] if expected_zone_names else '<zone>'}"]),
                [DOCS["pe_dns"], DOCS["pe_dns_integration"]]))
        elif zone_configs and expected_zone_names:
            used = {_name(c["zone_id"]).casefold() for c in zone_configs}
            if not used & set(expected_zone_names):
                bad = True
                findings.append(_finding(
                    f"PE-WRONG-ZONE:{name}", "high", rid,
                    f"Private endpoint {name} ({', '.join(group_ids)}) is registered in the wrong zone",
                    {"groupIds": group_ids, "zones_used": sorted(used), "expected_zones": expected_zone_names},
                    "Clients resolve the public FQDN via its privatelink CNAME; only the recommended zone name "
                    "is consulted. Register the PE in the recommended zone.",
                    _human([f"az network private-endpoint dns-zone-group list -g {rg} --endpoint-name {name} -o json"]),
                    [DOCS["pe_dns"]]))

        # Zone existence and VNet links.
        pe_vnet = _vnet_of_subnet(_ref(p.get("subnet")))
        need_vnets = resolver_vnets or ([_norm(pe_vnet)] if pe_vnet else [])
        for cfg in sorted(zone_configs, key=lambda c: _norm(c["zone_id"])):
            zid = _norm(cfg["zone_id"])
            zname = _name(cfg["zone_id"])
            if zones is not None and zid not in zone_ids:
                bad = True
                findings.append(_finding(
                    f"PE-ZONE-MISSING:{name}:{zname}", "high", rid,
                    f"Zone {zname} referenced by {name} was not found in scope",
                    {"privateDnsZoneId": cfg["zone_id"]},
                    "The zone was deleted or lives outside the managed scope. Confirm where it is hosted.",
                    _human([f"az network private-dns zone list --query \"[?name=='{zname}'].id\" -o tsv"]),
                    [DOCS["pe_dns"]]))
                continue
            if links is None:
                continue
            zone_links = links_by_zone.get(zid, [])
            linked = {}
            for link in zone_links:
                lp = _props(link)
                linked[_norm(_ref(lp.get("virtualNetwork")))] = link
                if (_text(lp.get("resolutionPolicy")) == "NxDomainRedirect"
                        and ("nx", _norm(link.get("id"))) not in reported_links):
                    reported_links.add(("nx", _norm(link.get("id"))))
                    findings.append(_finding(
                        f"PE-LINK-NXDOMAIN-REDIRECT:{zname}:{_name(link.get('id'))}", "info", _text(link.get("id")),
                        f"Link {_name(link.get('id'))} on {zname} uses NxDomainRedirect (fallback to internet)",
                        {"resolutionPolicy": "NxDomainRedirect"},
                        "Missing records resolve to the public endpoint instead of NXDOMAIN. Expected when "
                        "intentional; otherwise it can mask a missing A record.",
                        _human([f"az network private-dns link vnet show -g {_rg(link.get('id'))} -z {zname} "
                                f"-n {_name(link.get('id'))} --query resolutionPolicy"]),
                        [DOCS["dns_fallback"], DOCS["nxdomain"]]))
            for vnet in need_vnets:
                link = linked.get(vnet)
                key = (zid, vnet)
                if link is None:
                    bad = True
                    if key in reported_links:
                        continue
                    reported_links.add(key)
                    findings.append(_finding(
                        f"PE-ZONE-NOT-LINKED:{zname}:{_name(vnet)}", "high", cfg["zone_id"],
                        f"Zone {zname} is not linked to VNet {_name(vnet)}",
                        {"zone": zname, "vnet": vnet, "linked_vnets": sorted(_name(v) for v in linked)},
                        "VMs in that VNet resolve the privatelink CNAME through public DNS and reach the public "
                        "endpoint (or fail). Link the zone to the VNet that hosts the resolver (human-run).",
                        _human([f"az network private-dns link vnet list -g {_rg(cfg['zone_id'])} -z {zname} -o table"]),
                        [DOCS["dns_links"], DOCS["pe_dns"]]))
                    continue
                state = _text(_props(link).get("virtualNetworkLinkState"))
                if state and state.casefold() not in _LINK_READY:
                    bad = True
                    findings.append(_finding(
                        f"PE-LINK-NOT-READY:{zname}:{_name(link.get('id'))}", "medium", _text(link.get("id")),
                        f"Link {_name(link.get('id'))} on {zname} is {state}",
                        {"virtualNetworkLinkState": state},
                        "The link is still provisioning; resolution is not guaranteed until Completed.",
                        _human([f"az network private-dns link vnet show -g {_rg(link.get('id'))} -z {zname} "
                                f"-n {_name(link.get('id'))}"]),
                        [DOCS["dns_links"]]))

        # A records.
        if records is not None and zone_configs:
            expected, source = _expected_records(pe, zone_configs)
            for (zname, rec), ips in sorted(expected.items()):
                zid_candidates = [_norm(c["zone_id"]) for c in zone_configs if _name(c["zone_id"]).casefold() == zname]
                found = None
                for zid in zid_candidates:
                    found = records_by_zone.get(zid, {}).get(rec) or found
                if found is None:
                    bad = True
                    findings.append(_finding(
                        f"PE-DNS-RECORD-MISSING:{zname}:{rec}", "critical", rid,
                        f"A record {rec}.{zname} for {name} is missing",
                        {"zone": zname, "record": rec, "expected_ips": sorted(ips), "expected_from": source},
                        "Clients get NXDOMAIN (or the public IP with NxDomainRedirect). Recreate the A record or "
                        "re-create the zone group so it re-registers (human-run).",
                        _human([f"az network private-dns record-set a list -g {_rg(zid_candidates[0] if zid_candidates else rid)} "
                                f"-z {zname} --query \"[].{{name:name,ips:aRecords[].ipv4Address}}\" -o table",
                                "# Change (review before running):",
                                f"# az network private-dns record-set a add-record -g <zone-rg> -z {zname} "
                                f"-n {rec} --ipv4-address {sorted(ips)[0] if ips else '<pe-ip>'}"]),
                        [DOCS["pe_dns"]]))
                    continue
                actual = {_text(a.get("ipv4Address")) for a in _props(found).get("aRecords") or []}
                if ips and actual != ips:
                    bad = True
                    findings.append(_finding(
                        f"PE-DNS-RECORD-MISMATCH:{zname}:{rec}", "critical", _text(found.get("id")),
                        f"A record {rec}.{zname} does not match the private endpoint IP",
                        {"expected_ips": sorted(ips), "actual_ips": sorted(actual)},
                        "The record points at a stale or different IP. Correct it to the PE NIC IP (human-run).",
                        _human([f"az network private-endpoint show -g {rg} -n {name} --query customDnsConfigs"]),
                        [DOCS["pe_dns"]]))
        if not bad:
            healthy += 1

    for check in sorted(checks or [], key=lambda c: (_text(c.get("fqdn")), _text(c.get("from")))):
        fqdn = _text(check.get("fqdn"))
        resolved = [_text(i) for i in check.get("resolved_ips") or []]
        origin = _text(check.get("from")) or "client"
        if not resolved:
            findings.append(_finding(
                f"PE-RESOLVE-NXDOMAIN:{fqdn}:{origin}", "critical", "",
                f"{fqdn} did not resolve from {origin}",
                {"fqdn": fqdn, "from": origin, "resolved_ips": []},
                "Name resolution failed: check the A record and the zone link for the client's resolver VNet.",
                _human([f"nslookup {fqdn}"]), [DOCS["pe_dns"]]))
        elif any(_is_public(ip) for ip in resolved):
            findings.append(_finding(
                f"PE-RESOLVES-PUBLIC:{fqdn}:{origin}", "critical", "",
                f"{fqdn} resolves to a public IP from {origin}",
                {"fqdn": fqdn, "from": origin, "resolved_ips": resolved},
                "The client is not using the private zone (missing link, conditional forwarder, or custom DNS).",
                _human([f"nslookup {fqdn}"]), [DOCS["pe_dns"], DOCS["pe_dns_integration"]]))
        elif pe_ips and not set(resolved) & pe_ips:
            findings.append(_finding(
                f"PE-RESOLVES-UNKNOWN-IP:{fqdn}:{origin}", "high", "",
                f"{fqdn} resolves to {', '.join(resolved)} which is not an in-scope PE IP",
                {"fqdn": fqdn, "from": origin, "resolved_ips": resolved},
                "Stale record or a different zone answers the query. Compare with customDnsConfigs.",
                _human([f"nslookup {fqdn}"]), [DOCS["pe_dns"]]))

    if pes and records is not None:
        for zid, recs in sorted(records_by_zone.items()):
            zname = _name(zid)
            if not zname.startswith("privatelink."):
                continue
            for rec_name, rec in sorted(recs.items()):
                ips = {_text(a.get("ipv4Address")) for a in _props(rec).get("aRecords") or []}
                if ips and not ips & pe_ips:
                    findings.append(_finding(
                        f"PE-DNS-STALE-RECORD:{zname}:{rec_name}", "info", _text(rec.get("id")),
                        f"A record {rec_name}.{zname} points to no in-scope private endpoint",
                        {"ips": sorted(ips)},
                        "Possibly a PE outside the managed scope, or a stale record left after deletion.",
                        "", [DOCS["pe_dns"]]))

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (_SEV_ORDER.index(f["severity"]), f["resource_id"].casefold(), f["id"]))
    total = len(pes)
    kpis = {"pe_dns_healthy_pct": round(100.0 * healthy / total, 1)} if total else {}
    metrics = [{"label": "Private endpoints healthy", "value": f"{healthy}/{total}",
                "detail": "approved, zone linked, A record matches",
                "tone": "neutral" if not total else ("good" if healthy == total else "critical")}]
    return {"skill": SKILL, "findings": findings, "evidence_gaps": gaps, "metrics": metrics,
            "kpis": kpis, "partial": bool(gaps), "warnings": warnings}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] != "-":
        with open(argv[0], encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.load(sys.stdin)
    json.dump(analyze(data), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
