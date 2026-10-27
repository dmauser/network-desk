"""NetOps SNAT and egress health — pure, offline, deterministic.

Scores SNAT port exhaustion and egress data-path health for public Standard Load Balancer
(outbound rules / load-balancing-rule SNAT) and Azure NAT Gateway from raw read-only Azure
responses that the agent already collected (RunAzCliReadCommands). Stdlib only: JSON in,
JSON out, no I/O, no clock, no network. Never executes or emits Azure writes;
`remediation_script` values are read-only verification commands or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "load_balancers": [<ARM loadBalancers object>],          # az network lb list
          # uses frontendIPConfigurations[].publicIPAddress, backendAddressPools[]
          # (.backendIPConfigurations / .loadBalancerBackendAddresses), outboundRules[]
          # (.allocatedOutboundPorts, .frontendIPConfigurations, .backendAddressPool),
          # loadBalancingRules[].disableOutboundSnat
      "nat_gateways": [<ARM natGateways object>],               # az network nat gateway list
          # uses publicIpAddresses, publicIpPrefixes, idleTimeoutInMinutes, subnets
      "metrics": [{"resource_id": "...", "metric": "UsedSnatPorts", "value": 950,
                   "aggregation": "Average",
                   "dimensions": {"BackendIPAddress": "10.1.0.4"}}],
          # az monitor metrics list, reduced to the PEAK value in the window per
          # resource + dimension combination (see SKILL.md)
      "thresholds": {"snat_warn_pct": 70, "snat_crit_pct": 85, "failed_conn_crit": 1000,
                     "min_allocated_ports": 1024}
    }

Metrics used (names and dimensions from the Azure Monitor supported-metrics reference):
Load Balancer ``UsedSnatPorts`` / ``AllocatedSnatPorts`` (BackendIPAddress, FrontendIPAddress,
ProtocolType), ``SnatConnectionCount`` (ConnectionState = Failed, BackendIPAddress),
``VipAvailability`` (data path), ``DipAvailability`` (health probe, BackendIPAddress);
NAT Gateway ``SNATConnectionCount`` (ConnectionState = Attempted / Failed), ``PacketDropCount``,
``DatapathAvailability``, ``TotalConnectionCount``.

Output: the NetOps result envelope (see netops-report-renderer/models.py). KPI:
``snat_peak_util_pct`` = highest UsedSnatPorts / AllocatedSnatPorts across LB backends.
"""

from __future__ import annotations

import json
import sys

SKILL = "netops-snat-egress"

DOCS = {
    "lb_metrics": "https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-loadbalancers-metrics",
    "nat_metrics_ref": "https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-natgateways-metrics",
    "lb_diagnostics": "https://learn.microsoft.com/azure/load-balancer/load-balancer-standard-diagnostics",
    "lb_outbound": "https://learn.microsoft.com/azure/load-balancer/load-balancer-outbound-connections",
    "lb_troubleshoot_outbound": "https://learn.microsoft.com/azure/load-balancer/troubleshoot-outbound-connection",
    "nat_metrics": "https://learn.microsoft.com/azure/nat-gateway/nat-metrics",
    "nat_troubleshoot": "https://learn.microsoft.com/azure/nat-gateway/troubleshoot-nat-connectivity",
    "nat_resource": "https://learn.microsoft.com/azure/nat-gateway/nat-gateway-resource",
}

DEFAULT_THRESHOLDS = {"snat_warn_pct": 70.0, "snat_crit_pct": 85.0, "failed_conn_crit": 1000.0,
                      "min_allocated_ports": 1024.0}
# Each public frontend IP provides 64,000 SNAT-eligible ports (load-balancer-outbound-connections).
LB_PORTS_PER_FRONTEND_IP = 64000
# Default NAT gateway TCP idle timeout (minutes); higher values hold SNAT ports longer.
NAT_DEFAULT_IDLE_MINUTES = 4

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


def _list(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


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


def _fmt(value):
    return f"{value:g}"


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


def _scope_filter(items, managed, id_getter, dropped, label):
    kept = []
    for item in items:
        if _in_scope(id_getter(item), managed):
            kept.append(item)
        else:
            dropped[label] = dropped.get(label, 0) + 1
    return kept


def _dims(row):
    dims = row.get("dimensions")
    return dims if isinstance(dims, dict) else {}


def _dim(row, key):
    dims = _dims(row)
    for k, v in dims.items():
        if _text(k).casefold() == key.casefold():
            return _text(v)
    return ""


def _rows(metrics, metric):
    return [m for m in metrics if _text(m.get("metric")).casefold() == metric.casefold()
            and _num(m.get("value")) is not None]


def _peak(rows, key_fn):
    """Max value per key (inputs may hold several samples or protocol splits per key)."""

    out = {}
    for row in rows:
        key = key_fn(row)
        value = _num(row.get("value"))
        if key not in out or value > out[key]:
            out[key] = value
    return out


def _is_nat(resource_id):
    return "/providers/microsoft.network/natgateways/" in _norm_id(resource_id)


def _is_lb(resource_id):
    return "/providers/microsoft.network/loadbalancers/" in _norm_id(resource_id)


def _metrics_cmd(rid, metric, aggregation, extra=""):
    return (f"az monitor metrics list --resource {rid} --metrics {metric} "
            f"--aggregation {aggregation} --interval PT1M{extra} -o json")


# --- load balancer configuration ----------------------------------------------------

def _public_frontends(lb):
    return {_norm_id(f.get("id")) for f in _list(_props(lb).get("frontendIPConfigurations"))
            if _ref(_props(f).get("publicIPAddress")) or _ref(_props(f).get("publicIPPrefix"))}


def _pool_size(lb, pool_id):
    for pool in _list(_props(lb).get("backendAddressPools")):
        if _norm_id(pool.get("id")) != _norm_id(pool_id):
            continue
        p = _props(pool)
        ipcfg = _list(p.get("backendIPConfigurations"))
        addrs = _list(p.get("loadBalancerBackendAddresses"))
        return max(len(ipcfg), len(addrs))
    return None


def _analyze_lb_config(lbs, thresholds, findings):
    """Outbound rule allocation and implicit (default) SNAT through load-balancing rules."""

    min_ports = thresholds["min_allocated_ports"]
    snat_lbs = []
    for lb in sorted(lbs, key=lambda x: _norm_id(x.get("id"))):
        rid = _text(lb.get("id"))
        name = _text(lb.get("name")) or _name(rid)
        p = _props(lb)
        public = _public_frontends(lb)
        rules = _list(p.get("outboundRules"))
        lb_rules = _list(p.get("loadBalancingRules"))
        if public and (rules or lb_rules):
            snat_lbs.append(lb)
        for rule in sorted(rules, key=lambda r: _norm_id(r.get("id")) or _text(r.get("name"))):
            rp = _props(rule)
            rname = _text(rule.get("name")) or _name(rule.get("id"))
            ports = _num(rp.get("allocatedOutboundPorts"))
            fes = _list(rp.get("frontendIPConfigurations"))
            pool_id = _ref(rp.get("backendAddressPool"))
            pool_size = _pool_size(lb, pool_id)
            evidence = {"allocatedOutboundPorts": None if ports is None else int(ports),
                        "frontend_ips": len(fes), "backend_pool": _name(pool_id),
                        "backend_instances": pool_size,
                        "idleTimeoutInMinutes": rp.get("idleTimeoutInMinutes"),
                        "protocol": _text(rp.get("protocol"))}
            if fes and pool_size:
                evidence["max_ports_per_instance"] = int(len(fes) * LB_PORTS_PER_FRONTEND_IP // pool_size)
            verify = _human([f"az network lb outbound-rule list -g {_rg(rid)} --lb-name {name} -o json",
                             f"az network lb address-pool list -g {_rg(rid)} --lb-name {name} -o json",
                             "# Change (review before running):",
                             f"# az network lb outbound-rule update -g {_rg(rid)} --lb-name {name} -n {rname} "
                             "--allocated-outbound-ports <ports-per-instance>"])
            if ports == 0:
                findings.append(_finding(
                    f"SNAT-LB-DEFAULT-PORTS:{name}:{rname}", "medium", rid,
                    f"Outbound rule {rname} on {name} uses default port allocation (allocatedOutboundPorts = 0)",
                    evidence,
                    "Default port allocation gives each backend a small, pool-size-dependent number of ports "
                    "(1,024 for 1-50 instances down to 32 for 801-1,000) and is not recommended for "
                    "production. Allocate ports explicitly on the outbound rule or move egress to NAT Gateway.",
                    verify, [DOCS["lb_outbound"]]))
            elif ports is not None and ports < min_ports:
                findings.append(_finding(
                    f"SNAT-LB-LOW-PORTS:{name}:{rname}", "low", rid,
                    f"Outbound rule {rname} on {name} allocates only {int(ports)} SNAT ports per instance",
                    dict(evidence, min_allocated_ports=int(min_ports)),
                    "Low per-instance allocation increases the risk of SNAT exhaustion for chatty backends. "
                    "Compare with UsedSnatPorts and, if headroom exists (frontend IPs x 64,000 / instances), "
                    "raise allocatedOutboundPorts or add frontend IPs.",
                    verify, [DOCS["lb_outbound"]]))
        if public and not rules:
            implicit = sorted(_text(r.get("name")) or _name(r.get("id")) for r in lb_rules
                              if not _props(r).get("disableOutboundSnat"))
            if implicit:
                findings.append(_finding(
                    f"SNAT-LB-RULE-DEFAULT-SNAT:{name}", "medium", rid,
                    f"{name} provides outbound SNAT through load-balancing rules (default port allocation)",
                    {"loadBalancingRules_with_outbound_snat": implicit, "outboundRules": 0},
                    "A load-balancing rule with disableOutboundSnat = false uses default port allocation. "
                    "Set disableOutboundSnat and define an explicit outbound rule, or use NAT Gateway.",
                    _human([f"az network lb rule list -g {_rg(rid)} --lb-name {name} "
                            "--query \"[].{name:name,disableOutboundSnat:disableOutboundSnat}\" -o table",
                            "# Change (review before running):",
                            f"# az network lb rule update -g {_rg(rid)} --lb-name {name} -n <rule> "
                            "--disable-outbound-snat true",
                            f"# az network lb outbound-rule create -g {_rg(rid)} --lb-name {name} -n <rule> "
                            "--frontend-ip-configs <fe> --address-pool <pool> --protocol All "
                            "--outbound-ports <ports-per-instance>"]),
                    [DOCS["lb_outbound"]]))
    return snat_lbs


# --- metrics ------------------------------------------------------------------------

def _analyze_lb_ports(metrics, thresholds, lbs_by_id, findings):
    def key(row):
        return (_norm_id(row.get("resource_id")), _dim(row, "BackendIPAddress"),
                _dim(row, "FrontendIPAddress"), _dim(row, "ProtocolType"))

    lb_metrics = [m for m in metrics if _is_lb(m.get("resource_id"))]
    used = _peak(_rows(lb_metrics, "UsedSnatPorts"), key)
    allocated = _peak(_rows(lb_metrics, "AllocatedSnatPorts"), key)
    rid_by_norm = {_norm_id(m.get("resource_id")): _text(m.get("resource_id")) for m in lb_metrics}
    warn, crit = thresholds["snat_warn_pct"], thresholds["snat_crit_pct"]
    utils = []
    for k in sorted(set(used) & set(allocated)):
        alloc = allocated[k]
        if not alloc:
            continue
        pct = round(100.0 * used[k] / alloc, 1)
        utils.append(pct)
        if pct < warn:
            continue
        nrid, backend, frontend, proto = k
        rid = rid_by_norm[nrid]
        name = _name(rid)
        detail = ":".join(x for x in (backend or "all-backends", frontend, proto) if x)
        evidence = {"UsedSnatPorts_peak": used[k], "AllocatedSnatPorts": alloc, "utilization_pct": pct,
                    "BackendIPAddress": backend, "FrontendIPAddress": frontend, "ProtocolType": proto,
                    "warn_pct": warn, "crit_pct": crit}
        lb = lbs_by_id.get(nrid)
        if lb:
            evidence["public_frontend_ips"] = len(_public_frontends(lb))
        findings.append(_finding(
            f"SNAT-LB-PORT-UTIL:{name}:{detail}", "critical" if pct >= crit else "high", rid,
            f"SNAT port utilization {pct:g}% on {name} backend {backend or 'all'}",
            evidence,
            "New outbound flows fail when a backend runs out of SNAT ports. Reuse connections (pooling, "
            "keep-alive), use Private Link for Azure PaaS, raise allocatedOutboundPorts or add frontend "
            "IPs, or move egress to NAT Gateway.",
            _human([_metrics_cmd(rid, "UsedSnatPorts AllocatedSnatPorts", "Average",
                                 " --dimension BackendIPAddress"),
                    f"az network lb outbound-rule list -g {_rg(rid)} --lb-name {name} -o table",
                    "# Change (review before running):",
                    f"# az network lb outbound-rule update -g {_rg(rid)} --lb-name {name} -n <rule> "
                    "--allocated-outbound-ports <ports-per-instance>"]),
            [DOCS["lb_diagnostics"], DOCS["lb_outbound"], DOCS["lb_troubleshoot_outbound"], DOCS["lb_metrics"]]))
    return utils


def _analyze_failed(metrics, thresholds, findings):
    """LB SnatConnectionCount and NAT SNATConnectionCount with ConnectionState = Failed."""

    crit = thresholds["failed_conn_crit"]
    failed_total = 0.0
    rows = [m for m in _rows(metrics, "SnatConnectionCount")
            if _dim(m, "ConnectionState").casefold() == "failed"]
    groups = {}
    for m in rows:
        key = (_norm_id(m.get("resource_id")), _dim(m, "BackendIPAddress"))
        entry = groups.setdefault(key, {"rid": _text(m.get("resource_id")), "total": 0.0})
        entry["total"] += _num(m.get("value"))
    nat_failed = set()
    for (nrid, backend), entry in sorted(groups.items()):
        total = entry["total"]
        if total <= 0:
            continue
        failed_total += total
        rid = entry["rid"]
        name = _name(rid)
        severity = "critical" if total >= crit else "high"
        evidence = {"failed_connections": total, "ConnectionState": "Failed", "critical_at": crit}
        if _is_nat(rid):
            nat_failed.add(nrid)
            findings.append(_finding(
                f"SNAT-NAT-FAILED-CONN:{name}", severity, rid,
                f"NAT gateway {name}: {_fmt(total)} failed SNAT connection(s)",
                evidence,
                "Failed connections above zero indicate SNAT port exhaustion or the NAT gateway connection "
                "limit (50,000 simultaneous connections per IP to a unique destination). Add public IPs or a "
                "prefix, reduce the idle timeout, and reuse connections.",
                _human([_metrics_cmd(rid, "SNATConnectionCount", "Total", " --dimension ConnectionState"),
                        _metrics_cmd(rid, "TotalConnectionCount", "Total"),
                        f"az network nat gateway show -g {_rg(rid)} -n {name} "
                        "--query \"{ips:publicIpAddresses,prefixes:publicIpPrefixes,idle:idleTimeoutInMinutes}\"",
                        "# Change (review before running):",
                        f"# az network nat gateway update -g {_rg(rid)} -n {name} --public-ip-addresses <pip1> <pip2>"]),
                [DOCS["nat_metrics"], DOCS["nat_troubleshoot"], DOCS["nat_metrics_ref"]]))
        else:
            evidence["BackendIPAddress"] = backend
            findings.append(_finding(
                f"SNAT-LB-FAILED-CONN:{name}:{backend or 'all-backends'}", severity, rid,
                f"{name}: {_fmt(total)} failed SNAT connection(s) from backend {backend or 'all'}",
                evidence,
                "Outbound flows failed to get a SNAT port. Correlate with UsedSnatPorts vs AllocatedSnatPorts "
                "for the same backend and apply the SNAT exhaustion mitigations.",
                _human([_metrics_cmd(rid, "SnatConnectionCount", "Total",
                                     " --dimension ConnectionState BackendIPAddress"),
                        _metrics_cmd(rid, "UsedSnatPorts AllocatedSnatPorts", "Average",
                                     " --dimension BackendIPAddress")]),
                [DOCS["lb_diagnostics"], DOCS["lb_troubleshoot_outbound"], DOCS["lb_metrics"]]))
    return failed_total, nat_failed


def _analyze_nat(metrics, nat_failed, nats_by_id, findings):
    nat_metrics = [m for m in metrics if _is_nat(m.get("resource_id"))]
    rid_of = {_norm_id(m.get("resource_id")): _text(m.get("resource_id")) for m in nat_metrics}
    drops = {}
    for m in _rows(nat_metrics, "PacketDropCount"):
        nrid = _norm_id(m.get("resource_id"))
        drops[nrid] = drops.get(nrid, 0.0) + _num(m.get("value"))
    for nrid, total in sorted(drops.items()):
        if total <= 0:
            continue
        rid = rid_of[nrid]
        name = _name(rid)
        with_failed = nrid in nat_failed
        findings.append(_finding(
            f"SNAT-NAT-PACKET-DROPS:{name}", "high" if with_failed else "medium", rid,
            f"NAT gateway {name}: {_fmt(total)} dropped packet(s)"
            + (" coinciding with failed SNAT connections" if with_failed else ""),
            {"PacketDropCount": total, "failed_snat_connections_same_window": with_failed},
            "Check whether drops coincide with failed SNAT connections (exhaustion) or high connection "
            "volume. On StandardV2 NAT Gateway, drops also indicate the connection flow rate limit.",
            _human([_metrics_cmd(rid, "PacketDropCount", "Total"),
                    _metrics_cmd(rid, "SNATConnectionCount", "Total", " --dimension ConnectionState")]),
            [DOCS["nat_metrics"], DOCS["nat_troubleshoot"], DOCS["nat_metrics_ref"]]))

    for nrid in sorted(nat_failed | set(k for k, v in drops.items() if v > 0)):
        nat = nats_by_id.get(nrid)
        if not nat:
            continue
        idle = _num(_props(nat).get("idleTimeoutInMinutes"))
        if idle is None or idle <= NAT_DEFAULT_IDLE_MINUTES:
            continue
        rid = _text(nat.get("id"))
        name = _text(nat.get("name")) or _name(rid)
        findings.append(_finding(
            f"SNAT-NAT-IDLE-TIMEOUT:{name}", "low", rid,
            f"NAT gateway {name}: TCP idle timeout {_fmt(idle)} min while connections fail or drop",
            {"idleTimeoutInMinutes": idle, "default_minutes": NAT_DEFAULT_IDLE_MINUTES},
            "An idle timeout above the 4-minute default holds SNAT ports longer and adds pressure on the "
            "port inventory. Prefer TCP keepalives with a shorter idle timeout.",
            _human([f"az network nat gateway show -g {_rg(rid)} -n {name} --query idleTimeoutInMinutes",
                    "# Change (review before running):",
                    f"# az network nat gateway update -g {_rg(rid)} -n {name} --idle-timeout 4"]),
            [DOCS["nat_resource"], DOCS["nat_troubleshoot"]]))


def _analyze_availability(metrics, findings):
    checks = (
        ("DatapathAvailability", _is_nat, "NAT gateway datapath availability", "high", "critical"),
        ("VipAvailability", _is_lb, "Load Balancer data path availability", "high", "critical"),
        ("DipAvailability", _is_lb, "Load Balancer health probe status", "medium", "high"),
    )
    lowest = {}
    for metric, kind, label, sev_partial, sev_zero in checks:
        rows = [m for m in _rows(metrics, metric) if kind(m.get("resource_id"))]

        def key(row):
            return (_norm_id(row.get("resource_id")), _dim(row, "FrontendIPAddress"),
                    _dim(row, "BackendIPAddress"), _dim(row, "BackendPort"))

        rid_of = {_norm_id(m.get("resource_id")): _text(m.get("resource_id")) for m in rows}
        minima = {}
        for row in rows:
            k = key(row)
            v = _num(row.get("value"))
            if k not in minima or v < minima[k]:
                minima[k] = v
        for k in sorted(minima):
            value = minima[k]
            if value >= 100:
                continue
            nrid, frontend, backend, port = k
            rid = rid_of[nrid]
            name = _name(rid)
            lowest[nrid] = min(lowest.get(nrid, 100.0), value)
            detail = ":".join(x for x in (frontend, backend, port) if x)
            nat = _is_nat(rid)
            findings.append(_finding(
                f"SNAT-{'NAT' if nat else 'LB'}-{metric.upper()}:{name}" + (f":{detail}" if detail else ""),
                sev_zero if value <= 0 else sev_partial, rid,
                f"{label} {_fmt(value)}% on {name}" + (f" ({detail})" if detail else ""),
                {"metric": metric, "min_average_pct": value, "dimensions": {
                    "FrontendIPAddress": frontend, "BackendIPAddress": backend, "BackendPort": port}},
                ("Datapath availability drops that coincide with connection failures point to SNAT "
                 "exhaustion, connection limits, timeouts, or removed public IPs / subnets."
                 if nat else
                 "Health probe status below 100% means backends failed probes; check the probe port and "
                 "the backend service." if metric == "DipAvailability" else
                 "Data path availability below 100% means the frontend was not reachable through the "
                 "load balancer for part of the window; check resource health and backend health."),
                _human([_metrics_cmd(rid, metric, "Average",
                                     "" if nat else " --dimension FrontendIPAddress"),
                        f"az resource show --ids {rid} --query properties.provisioningState"]),
                [DOCS["nat_troubleshoot"], DOCS["nat_metrics"]] if nat else
                [DOCS["lb_diagnostics"], DOCS["lb_metrics"]]))
    return lowest


# --- entry point --------------------------------------------------------------------

def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    raw_thresholds = data.get("thresholds") or {}
    if not isinstance(raw_thresholds, dict):
        raise ValueError("thresholds must be an object")
    thresholds = dict(DEFAULT_THRESHOLDS)
    for k, v in raw_thresholds.items():
        if k in DEFAULT_THRESHOLDS and _num(v) is not None:
            thresholds[k] = _num(v)
    managed = data.get("managed_scopes")
    if managed is not None:
        if not isinstance(managed, list):
            raise ValueError("managed_scopes must be an array or null")
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

    lbs = items("load_balancers", lambda x: x.get("id"))
    nats = items("nat_gateways", lambda x: x.get("id"))
    metrics = items("metrics", lambda m: m.get("resource_id"))

    if lbs is None:
        gaps.append("load_balancers not collected (az network lb list).")
    if nats is None:
        gaps.append("nat_gateways not collected (az network nat gateway list).")
    if metrics is None:
        gaps.append("metrics not collected (az monitor metrics list); SNAT utilization, failed "
                    "connections, packet drops and availability not evaluated.")

    snat_lbs = _analyze_lb_config(lbs or [], thresholds, findings)
    lbs_by_id = {_norm_id(x.get("id")): x for x in lbs or []}
    nats_by_id = {_norm_id(x.get("id")): x for x in nats or []}

    utils, failed_total, lowest = [], 0.0, {}
    if metrics is not None:
        utils = _analyze_lb_ports(metrics, thresholds, lbs_by_id, findings)
        failed_total, nat_failed = _analyze_failed(metrics, thresholds, findings)
        _analyze_nat(metrics, nat_failed, nats_by_id, findings)
        lowest = _analyze_availability(metrics, findings)

        def has(nrid, names):
            wanted = {n.casefold() for n in names}
            return any(_norm_id(m.get("resource_id")) == nrid and _text(m.get("metric")).casefold() in wanted
                       for m in metrics)

        missing_lb = sorted(_name(x.get("id")) for x in snat_lbs
                            if not has(_norm_id(x.get("id")), ("UsedSnatPorts", "AllocatedSnatPorts")))
        if missing_lb:
            gaps.append("SNAT port metrics (UsedSnatPorts / AllocatedSnatPorts) not collected for "
                        + ", ".join(missing_lb) + ".")
        missing_nat = sorted(_name(x.get("id")) for x in nats or []
                             if not has(_norm_id(x.get("id")), ("SNATConnectionCount",)))
        if missing_nat:
            gaps.append("SNATConnectionCount (ConnectionState) not collected for NAT gateway(s) "
                        + ", ".join(missing_nat) + ".")

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"]), f["resource_id"].casefold(), f["id"]))

    kpis = {}
    peak = max(utils) if utils else None
    if peak is not None:
        kpis["snat_peak_util_pct"] = peak
    warn, crit = thresholds["snat_warn_pct"], thresholds["snat_crit_pct"]
    metric_rows = [
        {"label": "Peak SNAT port utilization", "value": "n/a" if peak is None else f"{peak:g}%",
         "detail": f"UsedSnatPorts / AllocatedSnatPorts across {len(utils)} LB backend sample(s)",
         "tone": "neutral" if peak is None else
                 ("critical" if peak >= crit else ("warning" if peak >= warn else "good"))},
        {"label": "Failed SNAT connections", "value": _fmt(failed_total),
         "detail": "ConnectionState = Failed (Load Balancer + NAT Gateway)",
         "tone": "neutral" if metrics is None else ("critical" if failed_total > 0 else "good")},
        {"label": "Egress resources", "value": f"{len(snat_lbs)} LB / {len(nats or [])} NAT GW",
         "detail": "Public LBs with SNAT rules and NAT gateways in scope", "tone": "neutral"},
        {"label": "Lowest data path availability",
         "value": "100%" if metrics is not None and not lowest else
                  ("n/a" if metrics is None else f"{min(lowest.values()):g}%"),
         "detail": "VipAvailability / DipAvailability / NAT DatapathAvailability (min average)",
         "tone": "neutral" if metrics is None else ("good" if not lowest else "critical")},
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
