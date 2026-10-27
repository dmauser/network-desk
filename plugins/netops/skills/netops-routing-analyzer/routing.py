"""NetOps routing analyzer — pure, offline, deterministic.

Analyzes route tables (UDRs), NIC effective routes, VNet peerings, Network Watcher next-hop
results, NVA NICs and optional data-plane probe evidence collected read-only by the agent
(RunAzCliReadCommands / execute_kusto_query). Detects UDR black holes (next hop ``None``),
peering misconfiguration, asymmetric routing through NVAs / Azure Firewall, NVA NICs with IP
forwarding off, NVA paths that fail in the data plane while the control plane is healthy
(guest OS forwarding), and MTU / MSS black holes (small payloads succeed, large ones hang).
Stdlib only: JSON in, JSON out, no I/O, no clock, no network. Never executes or emits Azure
writes; `remediation_script` values are read-only verification commands or commented,
human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,    # from netops-managed-scope
      "route_tables": [<ARM routeTables object>],                 # az network route-table list
      "effective_routes": [{"nic_id": "...", "value": [<EffectiveRoute>]}],
                                                                  # az network nic show-effective-route-table
      "vnet_peerings": [{"vnet_id": "...", "value": [<VirtualNetworkPeering>]}],
                                                                  # az network vnet peering list
      "nics": [<ARM networkInterfaces object>],                   # az network nic list
      "next_hop_checks": [{"vm_id": "...", "source_ip": "...", "dest_ip": "...",
                           "nextHopType": "...", "nextHopIpAddress": "...",
                           "routeTableId": "..."}],               # az network watcher show-next-hop (optional)
      "flows": [{"name": "...", "source_nic_id": "...", "destination_ip": "...",
                 "return_nic_id": "...", "source_ip": "..."}],    # optional pairs for asymmetry analysis
      "path_checks": [{"path": "...", "check": "small"|"large"|..., "payload_bytes": 64,
                       "result": "ok"|"pass"|"fail"|"timeout"|..., "via_nva": "10.0.2.4",
                       "source": "...", "destination": "...", "detail": "...",
                       "source_resource_id": "..."}],             # client probes / Connection Monitor rows
      "thresholds": {"large_payload_bytes": 1400}
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py). KPI
``asymmetric_paths`` = number of black-holed or asymmetric paths found.
"""

from __future__ import annotations

import ipaddress
import json
import sys

SKILL = "netops-routing-analyzer"

DOCS = {
    "udr": "https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview",
    "route_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/route-tables/get",
    "effective_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get-effective-route-table",
    "next_hop": "https://learn.microsoft.com/rest/api/network-watcher/network-watchers/get-next-hop",
    "peering_manage": "https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-peering",
    "peering_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/virtual-network-peerings/get",
    "peering_troubleshoot": "https://learn.microsoft.com/troubleshoot/azure/virtual-network/virtual-network-troubleshoot-peering-issues",
    "nic_rest": "https://learn.microsoft.com/rest/api/virtualnetwork/network-interfaces/get",
    "nic_manage": "https://learn.microsoft.com/azure/virtual-network/virtual-network-network-interface",
    "nva_troubleshoot": "https://learn.microsoft.com/troubleshoot/azure/virtual-network/virtual-network-troubleshoot-nva",
    "fw_asymmetric": "https://learn.microsoft.com/azure/firewall/integrate-lb",
    "tcpip_tuning": "https://learn.microsoft.com/azure/virtual-network/virtual-network-tcpip-performance-tuning",
    "vm_mtu": "https://learn.microsoft.com/azure/virtual-network/how-to-virtual-machine-mtu",
    "cm_overview": "https://learn.microsoft.com/azure/network-watcher/connection-monitor-overview",
    "cm_table": "https://learn.microsoft.com/azure/azure-monitor/reference/tables/nwconnectionmonitortestresult",
}

# Large enough to exceed a 1,400-byte tunnel MTU (Learn: MSS clamp 1,350 / tunnel MTU 1,400).
DEFAULT_THRESHOLDS = {"large_payload_bytes": 1400}

SEVERITIES = ("critical", "high", "medium", "low", "info")
# Finding codes that count toward the asymmetric_paths KPI (black-holed or asymmetric paths).
KPI_CODES = ("RT-BLACKHOLE", "RT-BLACKHOLE-EFFECTIVE", "RT-NEXTHOP-NONE", "RT-FLOW-BLACKHOLE",
             "RT-PEERING-NOT-CONNECTED", "RT-PEERING-ACCESS-DISABLED", "RT-ASYMMETRIC",
             "RT-NVA-IPFWD-OFF", "RT-NVA-DATAPLANE", "RT-MTU-BLACKHOLE")

_OK = {"ok", "pass", "passed", "success", "succeeded", "true", "reachable", "200"}
_FAIL = {"fail", "failed", "failure", "timeout", "timedout", "timed out", "hang", "hung", "error",
         "false", "unreachable", "reset", "dropped"}
_SOURCE_RANK = {"user": 0, "virtualnetworkgateway": 1, "default": 2}


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


def _net(prefix):
    try:
        return ipaddress.ip_network(_text(prefix), strict=False)
    except ValueError:
        return None


def _ip(value):
    try:
        return ipaddress.ip_address(_text(value))
    except ValueError:
        return None


def _list(value):
    if isinstance(value, list):
        return value
    return [] if value is None or value == "" else [value]


def _hop(value):
    return _text(value).casefold()


def _scope_filter(items, managed, id_getter, dropped, label):
    kept = []
    for item in items:
        if _in_scope(id_getter(item), managed):
            kept.append(item)
        else:
            dropped[label] = dropped.get(label, 0) + 1
    return kept


def _wrapped_values(entry):
    value = entry.get("value")
    if isinstance(value, dict):
        value = value.get("value")
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _lpm(routes, ip):
    """Longest-prefix match of ``ip`` over effective routes (Active only). Ties: User > BGP > Default."""

    addr = _ip(ip)
    if addr is None:
        return None, None
    best = None
    for route in routes:
        p = _props(route)
        state = _text(p.get("state"))
        if state and state.casefold() != "active":
            continue
        for prefix in _list(p.get("addressPrefix")):
            net = _net(prefix)
            if net is None or net.version != addr.version or addr not in net:
                continue
            rank = (-net.prefixlen, _SOURCE_RANK.get(_text(p.get("source")).casefold(), 3))
            if best is None or rank < best[0]:
                best = (rank, str(net), p)
    return (best[1], best[2]) if best else (None, None)


def _hop_ips(p):
    return sorted({_text(x) for x in _list(p.get("nextHopIpAddress")) if _text(x)})


def _nic_ips(nic):
    ips = []
    for cfg in _props(nic).get("ipConfigurations") or []:
        ip = _text(_props(cfg).get("privateIPAddress"))
        if ip:
            ips.append(ip)
    return ips


# --- analysis -----------------------------------------------------------------------

class _Ctx:
    def __init__(self):
        self.findings = []
        self.blackholes = {}     # normalized prefix -> finding
        self.nva_ips = {}        # ip -> sorted set of sources (strings)

    def add_nva(self, ip, source):
        if _ip(ip) is not None:
            self.nva_ips.setdefault(_text(ip), set()).add(source)

    def observe(self, prefix, observation):
        finding = self.blackholes.get(prefix)
        if finding is None:
            return False
        finding["evidence"].setdefault("observed_on", []).append(observation)
        return True


def _analyze_route_tables(tables, ctx):
    udr_count = 0
    for table in sorted(tables, key=lambda t: _norm_id(t.get("id"))):
        rid = _text(table.get("id"))
        p = _props(table)
        tname = _text(table.get("name")) or _name(rid)
        subnets = sorted(_name(_ref(s)) for s in p.get("subnets") or [] if _ref(s))
        for route in sorted(p.get("routes") or [], key=lambda r: _text(r.get("name"))):
            if not isinstance(route, dict):
                continue
            udr_count += 1
            rp = _props(route)
            rname = _text(route.get("name")) or _text(rp.get("name"))
            hop = _hop(rp.get("nextHopType"))
            prefix = _text(rp.get("addressPrefix"))
            if hop == "virtualappliance":
                ctx.add_nva(rp.get("nextHopIpAddress"), f"route-table {tname}/{rname}")
            if hop != "none":
                continue
            net = _net(prefix)
            key = str(net) if net else prefix.casefold()
            finding = _finding(
                f"RT-BLACKHOLE:{tname}:{rname}", "critical", rid,
                f"UDR {rname} in {tname} black-holes {prefix} (next hop None)",
                {"route": rname, "addressPrefix": prefix, "nextHopType": "None",
                 "associated_subnets": subnets},
                "Traffic routed to the None next hop type is dropped. Confirm whether this route is "
                "intentional; if not, point it at the correct next hop (VirtualAppliance / "
                "VirtualNetworkGateway) or remove it so the system or BGP route applies.",
                _human([f"az network route-table route show -g {_rg(rid)} --route-table-name {tname} -n {rname}",
                        f"az network route-table show -g {_rg(rid)} -n {tname} --query \"subnets[].id\"",
                        "# Change (review before running):",
                        f"# az network route-table route delete -g {_rg(rid)} --route-table-name {tname} -n {rname}"]),
                [DOCS["udr"], DOCS["route_rest"]])
            ctx.findings.append(finding)
            ctx.blackholes.setdefault(key, finding)
    return udr_count


def _analyze_effective(effective, ctx):
    by_nic = {}
    for entry in sorted(effective, key=lambda e: _norm_id(e.get("nic_id"))):
        nic_id = _text(entry.get("nic_id"))
        routes = _wrapped_values(entry)
        by_nic[_norm_id(nic_id)] = routes
        nic = _name(nic_id)
        for route in routes:
            p = _props(route)
            hop = _hop(p.get("nextHopType"))
            if hop == "virtualappliance":
                for ip in _hop_ips(p):
                    ctx.add_nva(ip, f"effective route on {nic}")
            state = _text(p.get("state")).casefold()
            if hop != "none" or _text(p.get("source")).casefold() != "user" or state not in ("", "active"):
                continue
            for prefix in sorted(_text(x) for x in _list(p.get("addressPrefix"))):
                net = _net(prefix)
                key = str(net) if net else prefix.casefold()
                obs = {"nic": nic, "addressPrefix": prefix, "source": "User", "state": "Active",
                       "route": _text(p.get("name"))}
                if ctx.observe(key, obs):
                    continue
                finding = _finding(
                    f"RT-BLACKHOLE-EFFECTIVE:{nic}:{prefix}", "critical", nic_id,
                    f"Effective route on {nic} sends {prefix} to None (traffic dropped)",
                    {"addressPrefix": prefix, "nextHopType": "None", "source": "User",
                     "route": _text(p.get("name")), "observed_on": [obs]},
                    "A user-defined route with next hop None is active on this NIC. Find the route "
                    "table associated with the NIC's subnet and correct or remove the route.",
                    _human([f"az network nic show-effective-route-table -g {_rg(nic_id)} -n {nic} -o table",
                            f"az network route-table list -g {_rg(nic_id)} -o table"]),
                    [DOCS["udr"], DOCS["effective_rest"]])
                ctx.findings.append(finding)
                ctx.blackholes[key] = finding
    return by_nic


def _analyze_next_hops(checks, tables, ctx):
    tables_by_id = {_norm_id(t.get("id")): t for t in tables or []}
    for check in sorted(checks, key=lambda c: (_norm_id(c.get("vm_id")), _text(c.get("source_ip")),
                                               _text(c.get("dest_ip")))):
        p = _props(check)
        hop = _hop(p.get("nextHopType"))
        vm_id = _text(check.get("vm_id"))
        dest = _text(check.get("dest_ip"))
        if hop == "virtualappliance":
            ctx.add_nva(p.get("nextHopIpAddress"), f"next-hop check {_name(vm_id)} -> {dest}")
            continue
        if hop != "none":
            continue
        rt_id = _text(p.get("routeTableId"))
        obs = {"next_hop_check": f"{_name(vm_id)} {_text(check.get('source_ip'))} -> {dest}",
               "routeTableId": rt_id}
        table = tables_by_id.get(_norm_id(rt_id))
        if table is not None:
            routes = [_props(r) for r in _props(table).get("routes") or [] if isinstance(r, dict)
                      and _hop(_props(r).get("nextHopType")) == "none"]
            prefix, _ = _lpm([{"addressPrefix": r.get("addressPrefix"), "source": "User"} for r in routes], dest)
            if prefix and ctx.observe(prefix, obs):
                continue
        system = rt_id.casefold() == "system route"
        vm = _name(vm_id) or "vm"
        ctx.findings.append(_finding(
            f"RT-NEXTHOP-NONE:{vm}:{dest}", "high" if system else "critical", vm_id,
            f"Network Watcher next hop from {vm} to {dest} is None "
            + ("(system route)" if system else "(user-defined route)"),
            {"source_ip": _text(check.get("source_ip")), "dest_ip": dest, "nextHopType": "None",
             "routeTableId": rt_id},
            "Traffic to this destination is dropped. For a system route, the destination is not in "
            "the VNet, a peered VNet or a learned prefix (check peering / gateway propagation); for a "
            "user-defined route, correct the route in the referenced route table.",
            _human([f"az network watcher show-next-hop -g {_rg(vm_id)} --vm {vm} "
                    f"--source-ip {_text(check.get('source_ip'))} --dest-ip {dest}"]),
            [DOCS["next_hop"], DOCS["udr"]]))


def _peering_index(peerings):
    index = {}
    for entry in peerings:
        vnet = _norm_id(entry.get("vnet_id"))
        for peer in _wrapped_values(entry):
            remote = _norm_id(_ref(_props(peer).get("remoteVirtualNetwork")))
            index[(vnet, remote)] = peer
    return index


def _remote_prefixes(p):
    prefixes = []
    for key in ("remoteAddressSpace", "remoteVirtualNetworkAddressSpace"):
        space = p.get(key) or {}
        prefixes.extend(_text(x) for x in space.get("addressPrefixes") or [])
    return sorted({x for x in prefixes if _net(x)})


def _analyze_peerings(peerings, ctx):
    total = connected = 0
    index = _peering_index(peerings)
    for entry in sorted(peerings, key=lambda e: _norm_id(e.get("vnet_id"))):
        vnet_id = _text(entry.get("vnet_id"))
        vnet = _name(vnet_id)
        for peer in sorted(_wrapped_values(entry), key=lambda x: _text(x.get("name"))):
            p = _props(peer)
            pname = _text(peer.get("name")) or _text(p.get("name"))
            rid = _text(peer.get("id")) or f"{vnet_id}/virtualNetworkPeerings/{pname}"
            remote_id = _ref(p.get("remoteVirtualNetwork"))
            remote = _name(remote_id)
            state = _text(p.get("peeringState")) or "Unknown"
            total += 1
            other = index.get((_norm_id(remote_id), _norm_id(vnet_id)))
            op = _props(other) if other else None
            remote_side = None if op is None else {
                "peeringState": _text(op.get("peeringState")),
                "allowVirtualNetworkAccess": op.get("allowVirtualNetworkAccess"),
                "allowForwardedTraffic": op.get("allowForwardedTraffic"),
                "allowGatewayTransit": op.get("allowGatewayTransit")}
            base = {"vnet": vnet, "peering": pname, "remote_vnet": remote, "peeringState": state,
                    "allowVirtualNetworkAccess": p.get("allowVirtualNetworkAccess"),
                    "allowForwardedTraffic": p.get("allowForwardedTraffic"),
                    "allowGatewayTransit": p.get("allowGatewayTransit"),
                    "useRemoteGateways": p.get("useRemoteGateways"),
                    "remote_side": remote_side if remote_side else "not collected"}
            show = (f"az network vnet peering show -g {_rg(vnet_id)} --vnet-name {vnet} -n {pname} "
                    "--query \"{state:peeringState,sync:peeringSyncLevel,access:allowVirtualNetworkAccess,"
                    "fwd:allowForwardedTraffic,gwTransit:allowGatewayTransit,remoteGw:useRemoteGateways}\"")
            if state == "Connected":
                connected += 1
            else:
                ctx.findings.append(_finding(
                    f"RT-PEERING-NOT-CONNECTED:{vnet}:{pname}",
                    "critical" if state in ("Disconnected", "Unknown") else "high", rid,
                    f"Peering {pname} ({vnet} -> {remote}) is {state}",
                    base,
                    "Disconnected means one of the two peering links was deleted; Initiated means the "
                    "remote side was never created. Traffic does not flow until both sides are "
                    "Connected: recreate the missing side.",
                    _human([show,
                            f"az network vnet peering list -g {_rg(remote_id)} --vnet-name {remote} -o table"]),
                    [DOCS["peering_manage"], DOCS["peering_troubleshoot"], DOCS["peering_rest"]]))
            if p.get("allowVirtualNetworkAccess") is False:
                one_way = bool(op and op.get("allowVirtualNetworkAccess") is True)
                ctx.findings.append(_finding(
                    f"RT-PEERING-ACCESS-DISABLED:{vnet}:{pname}", "critical", rid,
                    f"Peering {pname} ({vnet} -> {remote}) has allowVirtualNetworkAccess=false"
                    + (" (one-way: the remote side allows access)" if one_way else ""),
                    dict(base, one_way=one_way),
                    "VMs in this VNet cannot access the remote VNet over the peering even though the "
                    "peering state can still show Connected. Re-enable virtual network access on this "
                    "side (compare both sides: the break often looks one-way).",
                    _human([show,
                            "# Change (review before running):",
                            f"# az network vnet peering update -g {_rg(vnet_id)} --vnet-name {vnet} -n {pname} "
                            "--set allowVirtualNetworkAccess=true"]),
                    [DOCS["peering_manage"], DOCS["peering_rest"]]))
            if p.get("allowForwardedTraffic") is False:
                prefixes = _remote_prefixes(p)
                nvas = sorted(ip for ip in ctx.nva_ips
                              if any(_ip(ip) in _net(x) for x in prefixes
                                     if _net(x).version == _ip(ip).version))
                reasons = []
                if nvas:
                    reasons.append("NVA/firewall next hop(s) " + ", ".join(nvas) + f" are in {remote}")
                if p.get("useRemoteGateways") is True:
                    reasons.append("this side uses the remote gateway")
                if op and op.get("allowGatewayTransit") is True:
                    reasons.append(f"{remote} offers gateway transit")
                if reasons:
                    ctx.findings.append(_finding(
                        f"RT-PEERING-FORWARDED-DISABLED:{vnet}:{pname}", "high", rid,
                        f"Peering {pname} ({vnet} -> {remote}) blocks forwarded traffic while {remote} "
                        "forwards traffic",
                        dict(base, reasons=reasons, nva_next_hops=nvas),
                        "Traffic forwarded by an NVA / firewall or gateway in the remote VNet (not "
                        "originating there) is not accepted over this peering. Enable "
                        "allowForwardedTraffic on this side.",
                        _human([show,
                                "# Change (review before running):",
                                f"# az network vnet peering update -g {_rg(vnet_id)} --vnet-name {vnet} -n {pname} "
                                "--set allowForwardedTraffic=true"]),
                        [DOCS["peering_manage"], DOCS["peering_rest"]]))
            sync = _text(p.get("peeringSyncLevel"))
            if sync and sync != "FullyInSync":
                ctx.findings.append(_finding(
                    f"RT-PEERING-NOT-SYNCED:{vnet}:{pname}", "medium", rid,
                    f"Peering {pname} ({vnet} -> {remote}) is {sync}",
                    dict(base, peeringSyncLevel=sync, remote_prefixes=_remote_prefixes(p)),
                    "The address space changed on one side and the peering was not synced; new "
                    "prefixes are not reachable over the peering until it is synced.",
                    _human([show,
                            "# Change (review before running):",
                            f"# az network vnet peering sync -g {_rg(vnet_id)} --vnet-name {vnet} -n {pname}"]),
                    [DOCS["peering_manage"], DOCS["peering_rest"]]))
    return total, connected


def _nic_ip_index(nics):
    index = {}
    for nic in sorted(nics, key=lambda n: _norm_id(n.get("id"))):
        for ip in _nic_ips(nic):
            index.setdefault(ip, nic)
    return index


def _analyze_flows(flows, by_nic, nic_index, ctx, gaps):
    ip_by_nic = {_norm_id(n.get("id")): _nic_ips(n) for n in nic_index.values()}
    for flow in sorted(flows, key=lambda f: (_text(f.get("name")), _norm_id(f.get("source_nic_id")))):
        name = _text(flow.get("name")) or "flow"
        src_nic = _text(flow.get("source_nic_id"))
        ret_nic = _text(flow.get("return_nic_id"))
        dest = _text(flow.get("destination_ip"))
        src_ip = _text(flow.get("source_ip")) or next(iter(ip_by_nic.get(_norm_id(src_nic), [])), "")
        missing = [_name(n) for n in (src_nic, ret_nic) if n and _norm_id(n) not in by_nic]
        if missing or not ret_nic or not src_ip:
            reason = ("effective routes not collected for " + ", ".join(missing)) if missing else \
                ("return_nic_id missing" if not ret_nic else "source_ip unknown (collect nics)")
            gaps.append(f"flow {name}: asymmetry check skipped ({reason}).")
            continue
        fwd_prefix, fwd = _lpm(by_nic[_norm_id(src_nic)], dest)
        ret_prefix, ret = _lpm(by_nic[_norm_id(ret_nic)], src_ip)
        hops = {}
        for direction, prefix, route, nic in (("forward", fwd_prefix, fwd, src_nic),
                                              ("return", ret_prefix, ret, ret_nic)):
            hop = _text((route or {}).get("nextHopType")) or "NoRoute"
            ips = _hop_ips(route or {})
            hops[direction] = {"nic": _name(nic), "matched_prefix": prefix, "nextHopType": hop,
                               "nextHopIpAddress": ips, "source": _text((route or {}).get("source"))}
            if hop.casefold() == "virtualappliance":
                for ip in ips:
                    ctx.add_nva(ip, f"flow {name} ({direction})")
            if hop.casefold() == "none":
                obs = {"flow": name, "direction": direction, "nic": _name(nic)}
                if prefix and ctx.observe(prefix, obs):
                    continue
                user = _text(route.get("source")).casefold() == "user"
                ctx.findings.append(_finding(
                    f"RT-FLOW-BLACKHOLE:{name}:{direction}", "critical" if user else "high", nic,
                    f"Flow {name}: {direction} path from {_name(nic)} matches {prefix} with next hop None",
                    {"flow": name, "direction": direction, "matched_prefix": prefix,
                     "source": _text(route.get("source"))},
                    "The longest-prefix match for this destination drops traffic. Correct the "
                    "route (UDR) or add the missing peering / gateway route.",
                    _human([f"az network nic show-effective-route-table -g {_rg(nic)} -n {_name(nic)} -o table"]),
                    [DOCS["udr"], DOCS["effective_rest"]]))
        f_hop, r_hop = hops["forward"], hops["return"]
        f_va = f_hop["nextHopType"].casefold() == "virtualappliance"
        r_va = r_hop["nextHopType"].casefold() == "virtualappliance"
        if not (f_va or r_va):
            continue
        if f_va and r_va and f_hop["nextHopIpAddress"] == r_hop["nextHopIpAddress"]:
            continue
        if f_va and r_va:
            why = "forward and return use different NVA / firewall IPs"
        elif f_va:
            why = "forward path goes through the NVA / firewall but the return path bypasses it"
        else:
            why = "return path goes through the NVA / firewall but the forward path bypasses it"
        ctx.findings.append(_finding(
            f"RT-ASYMMETRIC:{name}", "high", src_nic,
            f"Asymmetric routing on flow {name}: {why}",
            {"flow": name, "source_ip": src_ip, "destination_ip": dest,
             "forward": f_hop, "return": r_hop},
            "Stateful NVAs / Azure Firewall drop the half of a session they never saw. Add a UDR on "
            "the return subnet that sends the source prefix to the same NVA / firewall IP (or the "
            "same internal load balancer frontend for an NVA HA pair).",
            _human([f"az network nic show-effective-route-table -g {_rg(src_nic)} -n {_name(src_nic)} -o table",
                    f"az network nic show-effective-route-table -g {_rg(ret_nic)} -n {_name(ret_nic)} -o table"]),
            [DOCS["udr"], DOCS["fw_asymmetric"], DOCS["effective_rest"]]))


def _analyze_ip_forwarding(nic_index, ctx):
    off = {}
    for ip in sorted(ctx.nva_ips):
        nic = nic_index.get(ip)
        if nic is None:
            continue
        p = _props(nic)
        if p.get("enableIPForwarding") is True:
            continue
        rid = _text(nic.get("id"))
        name = _text(nic.get("name")) or _name(rid)
        off[ip] = name
        ctx.findings.append(_finding(
            f"RT-NVA-IPFWD-OFF:{name}", "high", rid,
            f"NVA next hop {ip} ({name}) has IP forwarding disabled on its NIC",
            {"nic": name, "ip": ip, "enableIPForwarding": p.get("enableIPForwarding"),
             "referenced_by": sorted(ctx.nva_ips[ip])},
            "Azure drops traffic sent to a NIC for an address it does not own unless IP forwarding "
            "is enabled on the NIC. Enable it on every NVA NIC that forwards traffic (and in the "
            "guest operating system).",
            _human([f"az network nic show -g {_rg(rid)} -n {name} --query enableIPForwarding",
                    "# Change (review before running):",
                    f"# az network nic update -g {_rg(rid)} -n {name} --ip-forwarding true"]),
            [DOCS["udr"], DOCS["nic_manage"], DOCS["nva_troubleshoot"], DOCS["nic_rest"]]))
    return off


def _classify_size(check, large_bytes):
    label = (_text(check.get("check")) + " " + _text(check.get("name"))).casefold()
    if "large" in label:
        return "large"
    if "small" in label:
        return "small"
    size = _num(check.get("payload_bytes"))
    if size is not None:
        return "large" if size >= large_bytes else "small"
    return "unknown"


def _classify_result(check):
    value = _text(check.get("result") or check.get("TestResult")).casefold()
    if value in _OK:
        return "ok"
    if value in _FAIL:
        return "fail"
    return "unknown"


def _analyze_paths(checks, ipfwd_off, thresholds, ctx, gaps):
    large_bytes = float(thresholds["large_payload_bytes"])
    control_faults = sorted(f["id"] for f in ctx.findings if f["severity"] == "critical"
                            or f["id"].startswith(("RT-ASYMMETRIC:", "RT-NVA-IPFWD-OFF:")))
    groups = {}
    for check in checks:
        key = _text(check.get("path")) or (_text(check.get("source")) + "->" + _text(check.get("destination")))
        groups.setdefault(key or "path", []).append(check)
    sizes_seen = set()
    passed = total = 0
    for path, rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
        summary = []
        ok, fail = [], []
        for row in rows:
            size = _classify_size(row, large_bytes)
            result = _classify_result(row)
            sizes_seen.add(size)
            total += 1
            passed += result == "ok"
            entry = {"check": _text(row.get("check")) or _text(row.get("name")), "size": size,
                     "payload_bytes": row.get("payload_bytes"), "result": _text(row.get("result")
                                                                                 or row.get("TestResult")),
                     "detail": _text(row.get("detail"))}
            summary.append(entry)
            if result == "ok":
                ok.append(size)
            elif result == "fail":
                fail.append(size)
        rid = _text(rows[0].get("source_resource_id"))
        via = sorted({_text(r.get("via_nva")) for r in rows if _text(r.get("via_nva"))})
        for ip in via:
            ctx.add_nva(ip, f"path check {path}")
        if fail and ok and set(fail) == {"large"} and set(ok) <= {"small"}:
            ctx.findings.append(_finding(
                f"RT-MTU-BLACKHOLE:{path}", "high", rid,
                f"Path {path}: large payloads fail while small succeed — suspect MTU/MSS black-hole",
                {"path": path, "checks": summary, "via_nva": via},
                "Small requests (and availability probes) succeed while large responses hang: a hop "
                "on the path drops packets above its MTU and the ICMP Fragmentation Needed reply does "
                "not reach the sender (PMTUD broken). Azure's default MTU is 1,500 bytes and larger "
                "MTUs are not supported through gateways, global peering or the internet; for VPN "
                "tunnels Learn recommends TCP MSS clamping to 1,350 bytes and tunnel MTU 1,400. "
                "Check guest/NVA MTU settings, MSS clamping on the NVA / VPN device and ICMP filtering.",
                _human([f"# From the source VM (guest OS, run by a human): ping <destination> -c 10 -M do -s 1472",
                        "#   (1472 = 1500 MTU - 28 bytes of IP/ICMP headers; lower -s until it succeeds "
                        "to find the path MTU)",
                        "# No Azure control-plane change is implied; review guest/NVA MTU and MSS clamping."]),
                [DOCS["tcpip_tuning"], DOCS["vm_mtu"]]))
            continue
        if not fail or ok:
            continue
        nva_off = [ipfwd_off[ip] for ip in via if ip in ipfwd_off]
        if via and not nva_off and not control_faults:
            ctx.findings.append(_finding(
                f"RT-NVA-DATAPLANE:{path}", "high", rid,
                f"Path {path} via NVA {', '.join(via)}: data plane fails, control plane healthy — "
                "check guest OS IP forwarding / NVA firewall",
                {"path": path, "via_nva": via, "checks": summary,
                 "control_plane": "no black hole, peering, asymmetry or NIC IP forwarding fault found"},
                "Azure-side routing and NIC IP forwarding look correct, but traffic through the NVA "
                "fails. The control plane cannot see the appliance OS: confirm IP forwarding is "
                "enabled inside the guest operating system and that the NVA's own firewall / routing "
                "allows the flow.",
                _human([f"az network nic list -g <nva-resource-group> --query \"[?ipConfigurations[?privateIPAddress=='{via[0]}']]."
                        "{name:name,ipForwarding:enableIPForwarding}\"",
                        "# Guest OS (run by a human on the NVA): confirm IP forwarding is enabled in the "
                        "operating system and the NVA firewall permits the flow."]),
                [DOCS["udr"], DOCS["nva_troubleshoot"], DOCS["nic_manage"]]))
            continue
        ctx.findings.append(_finding(
            f"RT-PATH-FAIL:{path}", "medium", rid,
            f"Path {path} fails on every check"
            + (" (consistent with control-plane findings)" if (control_faults or nva_off) else ""),
            {"path": path, "via_nva": via, "checks": summary,
             "related_findings": sorted(control_faults + [f"RT-NVA-IPFWD-OFF:{n}" for n in nva_off])},
            "Fix the related control-plane findings first, then re-run the probe. If none are listed, "
            "check NSGs / firewall rules on the path (netops-nsg-firewall-audit).",
            _human(["# Re-run the client probe after addressing the related findings."]),
            [DOCS["udr"], DOCS["cm_overview"]]))
    if checks and "large" not in sizes_seen:
        gaps.append("path_checks contain only small-payload checks: availability probes measure only small "
                    "requests (Connection Monitor / health probes stay green), so an MTU/MSS black-hole "
                    "where large responses hang stays invisible; add a large-payload check "
                    f"(>= {int(large_bytes)} bytes, for example ping -M do -s 1472 or a large download).")
    return passed, total


def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    thresholds = dict(DEFAULT_THRESHOLDS)
    raw_thresholds = data.get("thresholds") or {}
    if not isinstance(raw_thresholds, dict):
        raise ValueError("thresholds must be an object")
    thresholds.update({k: v for k, v in raw_thresholds.items() if k in DEFAULT_THRESHOLDS})
    managed = data.get("managed_scopes")
    if managed is not None:
        if not isinstance(managed, list):
            raise ValueError("managed_scopes must be an array or null")
        managed = [_norm_id(s) for s in managed if _norm_id(s)]

    gaps, warnings = [], []
    dropped = {}

    def items(key, id_getter, optional_id=False):
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        rows = [v for v in value if isinstance(v, dict)]
        if optional_id:
            keep = [r for r in rows if not _text(id_getter(r))]
            return keep + _scope_filter([r for r in rows if _text(id_getter(r))], managed, id_getter,
                                        dropped, key)
        return _scope_filter(rows, managed, id_getter, dropped, key)

    tables = items("route_tables", lambda t: t.get("id"))
    effective = items("effective_routes", lambda e: e.get("nic_id"))
    peerings = items("vnet_peerings", lambda e: e.get("vnet_id"))
    nics = items("nics", lambda n: n.get("id"))
    next_hops = items("next_hop_checks", lambda c: c.get("vm_id"))
    flows = items("flows", lambda f: f.get("source_nic_id"))
    paths = items("path_checks", lambda c: c.get("source_resource_id"), optional_id=True)

    if tables is None:
        gaps.append("route_tables not collected (az network route-table list); UDR black-hole check skipped.")
    if effective is None:
        gaps.append("effective_routes not collected (az network nic show-effective-route-table is a POST "
                    "diagnostic needing networkInterfaces/effectiveRouteTable/action).")
    if peerings is None:
        gaps.append("vnet_peerings not collected (az network vnet peering list).")
    if nics is None:
        gaps.append("nics not collected (az network nic list); NVA IP forwarding check skipped.")
    if paths is None:
        gaps.append("path_checks not collected (client probe results or NWConnectionMonitorTestResult); "
                    "data-plane checks skipped.")

    ctx = _Ctx()
    udr_count = _analyze_route_tables(tables or [], ctx)
    by_nic = _analyze_effective(effective or [], ctx)
    if next_hops:
        _analyze_next_hops(next_hops, tables, ctx)
    nic_index = _nic_ip_index(nics or [])
    if flows:
        _analyze_flows(flows, by_nic, nic_index, ctx, gaps)
    for check in paths or []:
        if _text(check.get("via_nva")):
            ctx.add_nva(check.get("via_nva"), f"path check {_text(check.get('path'))}")
    peer_total = peer_up = 0
    if peerings is not None:
        peer_total, peer_up = _analyze_peerings(peerings, ctx)
    ipfwd_off = _analyze_ip_forwarding(nic_index, ctx) if nics is not None else {}
    passed = checks_total = 0
    if paths is not None:
        passed, checks_total = _analyze_paths(paths, ipfwd_off, thresholds, ctx, gaps)
    if ctx.nva_ips and not paths:
        gaps.append("VirtualAppliance next hop(s) " + ", ".join(sorted(ctx.nva_ips)) + " in path but no "
                    "data-plane evidence (path_checks): the control plane cannot see guest OS forwarding "
                    "(IP forwarding inside the appliance OS) or the NVA's own firewall; add a client "
                    "probe through the NVA path.")

    findings = ctx.findings
    for f in findings:
        if isinstance(f["evidence"], dict) and isinstance(f["evidence"].get("observed_on"), list):
            f["evidence"]["observed_on"] = sorted(f["evidence"]["observed_on"],
                                                  key=lambda o: json.dumps(o, sort_keys=True))

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["resource_id"].casefold(), f["id"]))
    asymmetric = sum(1 for f in findings if f["id"].split(":", 1)[0] in KPI_CODES)
    collected = any(x is not None for x in (tables, effective, peerings, flows, paths, next_hops))
    kpis = {"asymmetric_paths": asymmetric} if collected else {}
    nva_off_count = len(ipfwd_off)
    metric_rows = [
        {"label": "Black-holed / asymmetric paths", "value": str(asymmetric),
         "detail": "UDR/next-hop None, peering down, asymmetric NVA path, NVA forwarding or MTU black hole",
         "tone": "good" if collected and not asymmetric else ("neutral" if not collected else "critical")},
        {"label": "Peerings connected", "value": f"{peer_up}/{peer_total}",
         "detail": "peeringState == Connected",
         "tone": "good" if peer_total and peer_up == peer_total else
                 ("neutral" if not peer_total else "critical")},
        {"label": "UDRs analyzed", "value": str(udr_count),
         "detail": f"{len(ctx.nva_ips)} NVA / firewall next hop IP(s) referenced", "tone": "neutral"},
        {"label": "NVA NICs with IP forwarding off", "value": str(nva_off_count),
         "detail": "enableIPForwarding on NICs that own a VirtualAppliance next hop IP",
         "tone": "neutral" if nics is None else ("critical" if nva_off_count else "good")},
        {"label": "Data-plane checks passed", "value": f"{passed}/{checks_total}",
         "detail": "client probes / Connection Monitor results",
         "tone": "good" if checks_total and passed == checks_total else
                 ("neutral" if not checks_total else "warning")},
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
