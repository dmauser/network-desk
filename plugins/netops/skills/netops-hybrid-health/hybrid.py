"""NetOps hybrid connectivity health — pure, offline, deterministic.

Scores VPN / ExpressRoute gateway, connection, tunnel and BGP health from raw read-only Azure
responses that the agent already collected (RunAzCliReadCommands / execute_kusto_query). Stdlib
only: JSON in, JSON out, no I/O, no clock, no network. Never executes or emits Azure writes;
`remediation_script` values are read-only verification commands or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "gateways":     [<ARM virtualNetworkGateways object>],     # az network vnet-gateway list/show
      "connections":  [<ARM connections object>],                # az network vpn-connection list/show
      "bgp_peers":    [{"gateway_id": "...", "value": [<BgpPeerStatus>]}],
                                                                 # az network vnet-gateway list-bgp-peer-status
      "er_circuits":  [<ARM expressRouteCircuits object>],       # az network express-route list/show
      "er_route_summaries": [{"circuit_id": "...", "peering": "AzurePrivatePeering",
                              "path": "primary", "value": [<RoutesTableSummary>]}],
                                                                 # az network express-route list-route-tables-summary
      "tunnel_events": [<AzureDiagnostics TunnelDiagnosticLog row>],   # KQL (see SKILL.md)
      "metrics": [{"resource_id": "...", "metric": "BgpPeerStatus", "value": 0,
                   "dimensions": {"BgpPeerAddress": "10.0.0.4"}}],  # az monitor metrics list
      "thresholds": {"flap_events": 3, "er_route_warn_pct": 80}
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py).
"""

from __future__ import annotations

import json
import sys

SKILL = "netops-hybrid-health"

DOCS = {
    "bgp_status": "https://learn.microsoft.com/rest/api/network-gateway/virtual-network-gateways/get-bgp-peer-status",
    "bgp_troubleshoot": "https://learn.microsoft.com/troubleshoot/azure/vpn-gateway/vpn-gateway-troubleshoot-bgp",
    "vpn_diag_logs": "https://learn.microsoft.com/azure/vpn-gateway/troubleshoot-vpn-with-azure-diagnostics",
    "vpn_monitor_ref": "https://learn.microsoft.com/azure/vpn-gateway/monitor-vpn-gateway-reference",
    "gw_metrics": "https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-virtualnetworkgateways-metrics",
    "er_workflows": "https://learn.microsoft.com/azure/expressroute/expressroute-workflows",
    "er_faq": "https://learn.microsoft.com/azure/expressroute/expressroute-faqs",
    "er_limits": "https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-networking-limits",
    "er_summary": "https://learn.microsoft.com/rest/api/expressroute/express-route-circuits/list-routes-table-summary",
    "er_monitor": "https://learn.microsoft.com/azure/expressroute/monitor-expressroute-reference",
}

DEFAULT_THRESHOLDS = {"flap_events": 3, "er_route_warn_pct": 80.0}
# ExpressRoute private peering: 4,000 IPv4 prefixes (Standard) / 10,000 with Premium.
ER_PRIVATE_PEERING_LIMIT = {"standard": 4000, "local": 4000, "premium": 10000}

INPUT_KEYS = ("gateways", "connections", "bgp_peers", "er_circuits", "er_route_summaries",
              "tunnel_events", "metrics")


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


def _pct(numerator, denominator):
    return round(100.0 * numerator / denominator, 1) if denominator else None


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


# --- analysis -----------------------------------------------------------------------

def _scope_filter(items, managed, id_getter, dropped, label):
    kept = []
    for item in items:
        if _in_scope(id_getter(item), managed):
            kept.append(item)
        else:
            dropped[label] = dropped.get(label, 0) + 1
    return kept


def _analyze_connections(connections, findings):
    total = connected = 0
    for conn in sorted(connections, key=lambda c: _norm_id(c.get("id"))):
        rid = _text(conn.get("id"))
        p = _props(conn)
        name = _text(conn.get("name")) or _name(rid)
        ctype = _text(p.get("connectionType")) or "IPsec"
        status = _text(p.get("connectionStatus")) or "Unknown"
        gw = _ref(p.get("virtualNetworkGateway1"))
        total += 1
        tunnels = [t for t in (p.get("tunnelConnectionStatus") or []) if isinstance(t, dict)]
        if status == "Connected":
            connected += 1
            down = [t for t in tunnels if _text(t.get("connectionStatus")) not in ("", "Connected")]
            for t in sorted(down, key=lambda t: _text(t.get("tunnel"))):
                tun = _text(t.get("tunnel"))
                findings.append(_finding(
                    f"HYB-TUNNEL-DEGRADED:{name}:{tun}", "medium", rid,
                    f"Connection {name}: tunnel {tun} is {_text(t.get('connectionStatus'))}",
                    {"connectionStatus": status, "tunnel": tun,
                     "tunnelStatus": _text(t.get("connectionStatus")),
                     "lastConnectionEstablishedUtcTime": _text(t.get("lastConnectionEstablishedUtcTime"))},
                    "One active-active / multi-instance tunnel is down; redundancy is lost. Check the "
                    "on-premises device peer for that gateway instance IP.",
                    _human([f"az network vpn-connection show -g {_rg(rid)} -n {name} "
                            "--query \"tunnelConnectionStatus\" -o table"]),
                    [DOCS["vpn_diag_logs"]]))
            ingress = _num(p.get("ingressBytesTransferred"))
            egress = _num(p.get("egressBytesTransferred"))
            if ctype.casefold() == "ipsec" and ingress == 0 and egress == 0:
                findings.append(_finding(
                    f"HYB-TUNNEL-NO-TRAFFIC:{name}", "low", rid,
                    f"Connection {name} is Connected but has transferred no bytes",
                    {"ingressBytesTransferred": 0, "egressBytesTransferred": 0},
                    "Control plane is up but no data has crossed the tunnel. Verify traffic selectors, "
                    "routing (learned routes / UDRs) and on-premises forwarding.",
                    _human([f"az network vpn-connection show -g {_rg(rid)} -n {name} "
                            "--query \"{status:connectionStatus,in:ingressBytesTransferred,out:egressBytesTransferred}\""]),
                    [DOCS["vpn_monitor_ref"]]))
            continue
        severity = "critical" if status in ("NotConnected", "Unknown") else "high"
        findings.append(_finding(
            f"HYB-CONN-NOT-CONNECTED:{name}", severity, rid,
            f"{ctype} connection {name} is {status}",
            {"connectionStatus": status, "connectionType": ctype, "gateway": _name(gw),
             "tunnels": [{"tunnel": _text(t.get("tunnel")), "status": _text(t.get("connectionStatus"))}
                         for t in sorted(tunnels, key=lambda t: _text(t.get("tunnel")))]},
            "Confirm the on-premises VPN device / service is running and reachable on UDP 500/4500, "
            "shared key and IKE/IPsec parameters match, then review IKEDiagnosticLog / "
            "TunnelDiagnosticLog for the disconnect reason.",
            _human([f"az network vpn-connection show -g {_rg(rid)} -n {name} "
                    "--query \"{status:connectionStatus,tunnels:tunnelConnectionStatus}\"",
                    "# KQL: AzureDiagnostics | where Category in (\"TunnelDiagnosticLog\",\"IKEDiagnosticLog\")"]),
            [DOCS["vpn_diag_logs"], DOCS["vpn_monitor_ref"]]))
    return total, connected


def _gateway_index(gateways):
    return {_norm_id(g.get("id")): g for g in gateways}


def _analyze_bgp(bgp_peers, gateways_by_id, findings):
    total = connected = 0
    seen_gateways = set()
    for entry in sorted(bgp_peers, key=lambda e: _norm_id(e.get("gateway_id"))):
        gid = _text(entry.get("gateway_id"))
        seen_gateways.add(_norm_id(gid))
        gname = _name(gid)
        peers = entry.get("value") if isinstance(entry.get("value"), list) else []
        for peer in sorted(peers, key=lambda p: _text(p.get("neighbor"))):
            neighbor = _text(peer.get("neighbor"))
            state = _text(peer.get("state")) or "Unknown"
            total += 1
            if state == "Connected":
                connected += 1
                continue
            findings.append(_finding(
                f"HYB-BGP-NOT-CONNECTED:{gname}:{neighbor}", "critical", gid,
                f"BGP peer {neighbor} on {gname} is {state}",
                {"state": state, "asn": peer.get("asn"), "localAddress": _text(peer.get("localAddress")),
                 "routesReceived": peer.get("routesReceived"),
                 "messagesReceived": peer.get("messagesReceived")},
                "BGP runs over the IPsec tunnel: fix the tunnel first, then verify peer IP / ASN on both "
                "sides and that the on-premises BGP speaker is running.",
                _human([f"az network vnet-gateway list-bgp-peer-status -g {_rg(gid)} -n {gname} -o table"]),
                [DOCS["bgp_status"], DOCS["bgp_troubleshoot"]]))
    return total, connected, seen_gateways


def _analyze_bgp_metrics(metrics, seen_gateways, findings):
    """Fallback when getBgpPeerStatus (POST) was not collected: BgpPeerStatus metric 1=up, 0=down."""

    total = connected = 0
    rows = [m for m in metrics if _text(m.get("metric")) == "BgpPeerStatus"
            and _norm_id(m.get("resource_id")) not in seen_gateways]
    for m in sorted(rows, key=lambda m: (_norm_id(m.get("resource_id")),
                                         _text((m.get("dimensions") or {}).get("BgpPeerAddress")))):
        value = _num(m.get("value"))
        if value is None:
            continue
        rid = _text(m.get("resource_id"))
        peer = _text((m.get("dimensions") or {}).get("BgpPeerAddress")) or "unknown-peer"
        total += 1
        if value >= 1:
            connected += 1
            continue
        findings.append(_finding(
            f"HYB-BGP-NOT-CONNECTED:{_name(rid)}:{peer}", "critical" if value == 0 else "high", rid,
            f"BGP peer {peer} on {_name(rid)} reports BgpPeerStatus {value:g} (1 = connected)",
            {"metric": "BgpPeerStatus", "average": value, "source": "Azure Monitor metric fallback"},
            "Average below 1 means the peer was down for all (0) or part of the window. Confirm with "
            "list-bgp-peer-status and RouteDiagnosticLog BgpDisconnectedEvent.",
            _human([f"az monitor metrics list --resource {rid} --metric BgpPeerStatus "
                    "--aggregation Average --interval PT5M --dimension BgpPeerAddress"]),
            [DOCS["bgp_troubleshoot"], DOCS["gw_metrics"]]))
    return total, connected


def _analyze_flaps(events, thresholds, findings):
    """Group TunnelDiagnosticLog rows per gateway resource + remote IP and classify the pattern."""

    groups = {}
    for row in events:
        op = _text(row.get("OperationName"))
        if op not in ("TunnelDisconnected", "TunnelConnected"):
            continue
        key = (_text(row.get("ResourceId") or row.get("Resource")), _text(row.get("remoteIP_s")))
        groups.setdefault(key, []).append(row)
    limit = int(thresholds["flap_events"])
    for (resource, remote), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: _text(r.get("TimeGenerated")))
        disconnects = [r for r in rows if _text(r.get("OperationName")) == "TunnelDisconnected"]
        if not disconnects:
            continue
        instances = sorted({_text(r.get("instance_s")) for r in disconnects if _text(r.get("instance_s"))})
        failover = same_instance = 0
        for idx, row in enumerate(rows):
            if _text(row.get("OperationName")) != "TunnelDisconnected":
                continue
            nxt = rows[idx + 1] if idx + 1 < len(rows) else None
            if not nxt or _text(nxt.get("OperationName")) != "TunnelConnected":
                continue
            if _text(nxt.get("instance_s")) != _text(row.get("instance_s")):
                failover += 1
            else:
                same_instance += 1
        last = rows[-1]
        still_down = _text(last.get("OperationName")) == "TunnelDisconnected"
        if len(disconnects) < limit and not still_down:
            continue
        if same_instance:
            pattern = "same-instance reconnects (DPD timeout, network loss or on-premises device)"
        elif failover:
            pattern = "instance failover / planned maintenance"
        else:
            pattern = "disconnected with no reconnect observed"
        severity = "high" if still_down or same_instance >= limit else "medium"
        name = _name(resource, resource) or "gateway"
        findings.append(_finding(
            f"HYB-TUNNEL-FLAP:{name}:{remote}", severity, resource if resource.startswith("/") else "",
            f"Tunnel to {remote} on {name}: {len(disconnects)} disconnect(s)"
            + (" and still down" if still_down else ""),
            {"disconnects": len(disconnects), "failover_pairs": failover,
             "same_instance": same_instance, "instances": instances,
             "first": _text(rows[0].get("TimeGenerated")), "last": _text(last.get("TimeGenerated")),
             "last_event": _text(last.get("OperationName")), "pattern": pattern},
            "Disconnect on one instance followed by connect on the other is failover/maintenance; "
            "repeated disconnect/reconnect on the same instance points to DPD, packet loss or the "
            "on-premises device. Correlate with GatewayDiagnosticLog and IKEDiagnosticLog.",
            _human(["# KQL (Log Analytics):",
                    "AzureDiagnostics | where Category == \"TunnelDiagnosticLog\" "
                    f"| where remoteIP_s == \"{remote}\" "
                    "| project TimeGenerated, OperationName, instance_s, remoteIP_s | order by TimeGenerated asc"]),
            [DOCS["vpn_diag_logs"]]))


def _analyze_tsmismatch(metrics, findings):
    for m in sorted(metrics, key=lambda m: (_norm_id(m.get("resource_id")), _text(m.get("metric")))):
        metric = _text(m.get("metric"))
        if metric not in ("TunnelEgressPacketDropTSMismatch", "TunnelIngressPacketDropTSMismatch"):
            continue
        value = _num(m.get("value"))
        if not value or value <= 0:
            continue
        rid = _text(m.get("resource_id"))
        conn = _text((m.get("dimensions") or {}).get("ConnectionName")) or _name(rid)
        findings.append(_finding(
            f"HYB-TS-MISMATCH:{_name(rid)}:{conn}:{metric}", "high", rid,
            f"{metric} = {value:g} on {conn}: traffic-selector mismatch drops",
            {"metric": metric, "total": value, "dimensions": m.get("dimensions") or {}},
            "Traffic selectors (policy-based / UsePolicyBasedTrafficSelectors) differ between Azure and "
            "the on-premises device. Align the address prefixes on both sides.",
            _human([f"az monitor metrics list --resource {rid} --metric {metric} "
                    "--aggregation Total --dimension ConnectionName"]),
            [DOCS["gw_metrics"], DOCS["vpn_monitor_ref"]]))


def _analyze_er(circuits, summaries, metrics, thresholds, findings):
    by_id = {_norm_id(c.get("id")): c for c in circuits}
    for circuit in sorted(circuits, key=lambda c: _norm_id(c.get("id"))):
        rid = _text(circuit.get("id"))
        p = _props(circuit)
        name = _text(circuit.get("name")) or _name(rid)
        sp_state = _text(p.get("serviceProviderProvisioningState"))
        circuit_state = _text(p.get("circuitProvisioningState"))
        if sp_state and sp_state != "Provisioned":
            findings.append(_finding(
                f"HYB-ER-NOT-PROVISIONED:{name}", "critical", rid,
                f"ExpressRoute circuit {name}: provider state is {sp_state}",
                {"serviceProviderProvisioningState": sp_state, "circuitProvisioningState": circuit_state},
                "The connectivity provider has not completed provisioning. Engage the provider with the "
                "circuit service key.",
                _human([f"az network express-route show -g {_rg(rid)} -n {name} "
                        "--query \"{provider:serviceProviderProvisioningState,circuit:circuitProvisioningState}\""]),
                [DOCS["er_workflows"]]))
        elif circuit_state and circuit_state != "Enabled":
            findings.append(_finding(
                f"HYB-ER-CIRCUIT-DISABLED:{name}", "critical", rid,
                f"ExpressRoute circuit {name}: circuit state is {circuit_state}",
                {"serviceProviderProvisioningState": sp_state, "circuitProvisioningState": circuit_state},
                "The circuit is not Enabled; open a support request with the circuit details.",
                _human([f"az network express-route show -g {_rg(rid)} -n {name}"]),
                [DOCS["er_workflows"]]))

    for m in sorted(metrics, key=lambda m: (_norm_id(m.get("resource_id")), _text(m.get("metric")),
                                            json.dumps(m.get("dimensions") or {}, sort_keys=True))):
        metric = _text(m.get("metric"))
        if metric not in ("BgpAvailability", "ArpAvailability"):
            continue
        value = _num(m.get("value"))
        if value is None or value >= 100:
            continue
        rid = _text(m.get("resource_id"))
        dims = m.get("dimensions") or {}
        peer = _text(dims.get("Peer")) or "all"
        peering = _text(dims.get("PeeringType")) or "peering"
        findings.append(_finding(
            f"HYB-ER-{metric.upper()}:{_name(rid)}:{peering}:{peer}",
            "critical" if value == 0 else "high", rid,
            f"ExpressRoute {metric} {value:g}% on {_name(rid)} ({peering}, {peer})",
            {"metric": metric, "value_pct": value, "dimensions": dims},
            "BGP/ARP availability below 100% means a link or session to the MSEE was lost. Check the "
            "customer/provider edge for that path and the ARP / route tables.",
            _human([f"az network express-route list-arp-tables -g {_rg(rid)} -n {_name(rid)} "
                    f"--peering-name {peering if peering != 'peering' else 'AzurePrivatePeering'} --path primary",
                    f"az monitor metrics list --resource {rid} --metric {metric} --aggregation Average"]),
            [DOCS["er_monitor"]]))

    warn_pct = float(thresholds["er_route_warn_pct"])
    for summary in sorted(summaries, key=lambda s: (_norm_id(s.get("circuit_id")), _text(s.get("peering")),
                                                    _text(s.get("path")))):
        cid = _text(summary.get("circuit_id"))
        circuit = by_id.get(_norm_id(cid), {})
        tier = _text((circuit.get("sku") or {}).get("tier")).casefold() or "standard"
        limit = ER_PRIVATE_PEERING_LIMIT.get(tier, 4000)
        peering = _text(summary.get("peering")) or "AzurePrivatePeering"
        path = _text(summary.get("path")) or "primary"
        for row in sorted(summary.get("value") or [], key=lambda r: _text(r.get("neighbor"))):
            neighbor = _text(row.get("neighbor"))
            raw = row.get("statePfxRcd")
            count = _num(raw)
            base = f"{_name(cid)}:{peering}:{path}:{neighbor}"
            if count is None:
                findings.append(_finding(
                    f"HYB-ER-BGP-DOWN:{base}", "critical", cid,
                    f"ExpressRoute {peering} {path} BGP to {neighbor} is {_text(raw) or 'not established'}",
                    {"statePfxRcd": _text(raw), "upDown": _text(row.get("upDown")), "as": row.get("as")},
                    "statePfxRcd shows a BGP state instead of a prefix count: the session is not "
                    "established. Check peer IPs, VLAN, ASN and MD5 on the customer edge.",
                    _human([f"az network express-route list-route-tables-summary -g {_rg(cid)} -n {_name(cid)} "
                            f"--peering-name {peering} --path {path} -o table"]),
                    [DOCS["er_summary"]]))
                continue
            if peering == "AzurePrivatePeering" and count >= limit * warn_pct / 100.0:
                findings.append(_finding(
                    f"HYB-ER-ROUTE-LIMIT:{base}", "critical" if count >= limit else "high", cid,
                    f"{int(count)} prefixes received on {_name(cid)} {path} ({int(count * 100 / limit)}% of {limit})",
                    {"statePfxRcd": int(count), "limit": limit, "sku_tier": tier or "standard"},
                    "Exceeding the private peering prefix limit drops the BGP session. Summarize "
                    "on-premises advertisements or move to Premium (10,000).",
                    _human([f"az network express-route list-route-tables-summary -g {_rg(cid)} -n {_name(cid)} "
                            f"--peering-name {peering} --path {path} -o table"]),
                    [DOCS["er_faq"], DOCS["er_limits"]]))


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
        return _scope_filter([v for v in value if isinstance(v, dict)], managed, id_getter, dropped, key)

    gateways = items("gateways", lambda g: g.get("id"))
    connections = items("connections", lambda c: c.get("id"))
    bgp_peers = items("bgp_peers", lambda e: e.get("gateway_id"))
    circuits = items("er_circuits", lambda c: c.get("id"))
    summaries = items("er_route_summaries", lambda s: s.get("circuit_id"))
    events = items("tunnel_events", lambda r: r.get("ResourceId") or r.get("_ResourceId") or r.get("Resource"))
    metrics = items("metrics", lambda m: m.get("resource_id"))

    if gateways is None:
        gaps.append("gateways not collected (az network vnet-gateway list).")
    if connections is None:
        gaps.append("connections not collected (az network vpn-connection list).")

    tunnels_total = tunnels_up = 0
    if connections is not None:
        tunnels_total, tunnels_up = _analyze_connections(connections, findings)

    bgp_total = bgp_up = 0
    seen = set()
    if bgp_peers is not None:
        bgp_total, bgp_up, seen = _analyze_bgp(bgp_peers, _gateway_index(gateways or []), findings)
    m_total, m_up = _analyze_bgp_metrics(metrics or [], seen, findings)
    bgp_total += m_total
    bgp_up += m_up
    bgp_gateways = [g for g in gateways or [] if _props(g).get("enableBgp")
                    and _text(_props(g).get("gatewayType")).casefold() == "vpn"]
    missing = sorted(_name(g.get("id")) for g in bgp_gateways
                     if _norm_id(g.get("id")) not in seen
                     and not any(_norm_id(m.get("resource_id")) == _norm_id(g.get("id"))
                                 and _text(m.get("metric")) == "BgpPeerStatus" for m in metrics or []))
    if missing:
        gaps.append("BGP peer status not collected for " + ", ".join(missing)
                    + " (list-bgp-peer-status is a POST diagnostic; fall back to the BgpPeerStatus metric).")

    if events is None:
        gaps.append("tunnel_events not collected (AzureDiagnostics TunnelDiagnosticLog); flap analysis skipped.")
    else:
        _analyze_flaps(events, thresholds, findings)
    if metrics is not None:
        _analyze_tsmismatch(metrics, findings)

    er_gateways = [g for g in gateways or [] if _text(_props(g).get("gatewayType")).casefold() == "expressroute"]
    if circuits is None and er_gateways:
        gaps.append("ExpressRoute gateways present but er_circuits not collected (az network express-route list).")
    if circuits is not None or summaries is not None:
        _analyze_er(circuits or [], summaries or [], metrics or [], thresholds, findings)
    elif metrics:
        _analyze_er([], [], metrics, thresholds, findings)
    if circuits and summaries is None:
        gaps.append("er_route_summaries not collected; prefix-limit check skipped "
                    "(az network express-route list-route-tables-summary).")

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (("critical", "high", "medium", "low", "info").index(f["severity"]),
                                 f["resource_id"].casefold(), f["id"]))
    kpis = {}
    tunnels_pct = _pct(tunnels_up, tunnels_total)
    bgp_pct = _pct(bgp_up, bgp_total)
    if tunnels_pct is not None:
        kpis["tunnels_connected_pct"] = tunnels_pct
    if bgp_pct is not None:
        kpis["bgp_peers_connected_pct"] = bgp_pct
    metric_rows = [
        {"label": "Connections connected", "value": f"{tunnels_up}/{tunnels_total}",
         "detail": "connectionStatus == Connected",
         "tone": "good" if tunnels_total and tunnels_up == tunnels_total else
                 ("neutral" if not tunnels_total else "critical")},
        {"label": "BGP peers connected", "value": f"{bgp_up}/{bgp_total}",
         "detail": "state == Connected (or BgpPeerStatus metric = 1)",
         "tone": "good" if bgp_total and bgp_up == bgp_total else
                 ("neutral" if not bgp_total else "critical")},
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
