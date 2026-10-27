"""NetOps subnet IP and gateway capacity forecast — pure, offline, deterministic.

Scores subnet IP utilization, forecasts exhaustion from usage history, checks special-subnet
sizing, VNet address-space headroom and gateway capacity metrics from raw read-only Azure
responses that the agent already collected (RunAzCliReadCommands). Stdlib only: JSON in, JSON
out, no I/O, no clock, no network. Never executes or emits Azure writes; `remediation_script`
values are read-only verification commands or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "vnets":  [<az network vnet list object>],                 # addressSpace.addressPrefixes, subnets[]
      "usages": [{"vnet_id": "...", "value": [<VirtualNetworkUsage>]}],
                 # az rest --method get --url .../virtualNetworks/<vnet>/usages?api-version=2026-01-01
                 # VirtualNetworkUsage: {"id": <subnet id>, "currentValue": n, "limit": <subnet size>,
                 #                       "name": {"value": "SubnetSpace"}, "unit": "Count"}
      "history": [{"subnet_id": "...", "as_of": "2025-01-01", "used": 120}],   # optional snapshots
      "as_of": "2025-01-14",                                     # date of `usages`; required to forecast
      "gateway_metrics": [{"resource_id": "...", "metric": "ExpressRouteGatewayCpuUtilization",
                           "value": 91, "limit": null, "dimensions": {}}],     # optional
                           # az monitor metrics list; `limit` is operator-supplied for non-percent
                           # metrics (for example the SKU aggregate throughput benchmark in bytes/s)
      "thresholds": {"subnet_warn_pct": 80, "subnet_crit_pct": 95, "forecast_days": 90,
                     "vnet_min_free_prefix": 29, "gateway_cpu_pct": 80, "gateway_util_pct": 80}
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py). KPI:
`subnets_over_threshold` = subnets whose utilization (currentValue / limit) is >= subnet_warn_pct.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import math
import sys

SKILL = "netops-ip-capacity"

DOCS = {
    "vnet_usage": "https://learn.microsoft.com/rest/api/virtualnetwork/virtual-networks/list-usage",
    "vnet_faq": "https://learn.microsoft.com/azure/virtual-network/virtual-networks-faq",
    "cli_vnet": "https://learn.microsoft.com/cli/azure/network/vnet",
    "cli_subnet": "https://learn.microsoft.com/cli/azure/network/vnet/subnet",
    "gw_subnet": "https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-about-vpn-gateway-settings",
    "fw_faq": "https://learn.microsoft.com/azure/firewall/firewall-faq",
    "bastion_subnet": "https://learn.microsoft.com/azure/bastion/configuration-settings",
    "gw_metrics": "https://learn.microsoft.com/azure/azure-monitor/reference/supported-metrics/microsoft-network-virtualnetworkgateways-metrics",
    "vpn_skus": "https://learn.microsoft.com/azure/vpn-gateway/about-gateway-skus",
    "er_metrics": "https://learn.microsoft.com/azure/expressroute/expressroute-monitoring-metrics-alerts",
}

DEFAULT_THRESHOLDS = {"subnet_warn_pct": 80.0, "subnet_crit_pct": 95.0, "forecast_days": 90,
                      "vnet_min_free_prefix": 29, "gateway_cpu_pct": 80.0, "gateway_util_pct": 80.0}

# Verified minimum sizes (prefix length; larger number = smaller subnet).
SPECIAL_SUBNETS = {
    "gatewaysubnet": (27, "gw_subnet",
                      "All VPN/ExpressRoute gateway SKUs except Basic require GatewaySubnet /27 or larger "
                      "(/29 is possible for the Basic SKU only)."),
    "azurefirewallsubnet": (26, "fw_faq",
                            "Azure Firewall needs a /26 AzureFirewallSubnet so it can scale out instances."),
    "azurebastionsubnet": (26, "bastion_subnet",
                           "AzureBastionSubnet must be /26 or larger for deployments on or after "
                           "November 2, 2021; older /27 subnets keep working but should be increased "
                           "to /26 for host scaling."),
}

# Percent metrics compared with gateway_cpu_pct.
CPU_METRICS = ("ExpressRouteGatewayCpuUtilization", "ScalableExpressRouteGatewayCpuUtilization")
# Absolute metrics compared with an operator-supplied `limit` (gateway_util_pct of limit).
LIMIT_METRICS = ("AverageBandwidth", "TunnelAverageBandwidth", "P2SConnectionCount",
                 "ExpressRouteGatewayBitsPerSecond", "ExpressRouteGatewayCountOfRoutesLearnedFromPeer")

INPUT_KEYS = ("vnets", "usages", "history", "gateway_metrics")


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


def _vnet_of(subnet_id):
    rid = _text(subnet_id).rstrip("/")
    lowered = rid.casefold()
    marker = "/subnets/"
    idx = lowered.rfind(marker)
    return rid[:idx] if idx >= 0 else ""


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_text(value))
    except ValueError:
        return None


def _date(value):
    text = _text(value)
    if len(text) < 10:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
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


def _scope_filter(items, managed, id_getter, dropped, label):
    kept = []
    for item in items:
        if _in_scope(id_getter(item), managed):
            kept.append(item)
        else:
            dropped[label] = dropped.get(label, 0) + 1
    return kept


def _subnet_prefixes(subnet):
    p = _props(subnet)
    prefixes = []
    if _text(p.get("addressPrefix")):
        prefixes.append(_text(p.get("addressPrefix")))
    for pfx in p.get("addressPrefixes") or []:
        if _text(pfx) and _text(pfx) not in prefixes:
            prefixes.append(_text(pfx))
    return prefixes


def _ipv4(prefix):
    try:
        net = ipaddress.ip_network(_text(prefix), strict=False)
    except ValueError:
        return None
    return net if net.version == 4 else None


def _usage_script(vnet_id):
    return (f"az rest --method get --url \"https://management.azure.com{_text(vnet_id)}"
            "/usages?api-version=2026-01-01\"")


# --- analysis -----------------------------------------------------------------------

def _usage_rows(usages):
    """Flatten [{vnet_id, value: [usage]}] into per-subnet rows (limit <= 0 is skipped)."""

    rows, skipped = {}, []
    for entry in usages:
        vnet_id = _text(entry.get("vnet_id"))
        values = entry.get("value")
        if not isinstance(values, list):
            continue
        for usage in values:
            if not isinstance(usage, dict):
                continue
            sid = _text(usage.get("id"))
            used = _num(usage.get("currentValue"))
            limit = _num(usage.get("limit"))
            if not sid or used is None:
                continue
            if limit is None or limit <= 0 or used < 0:
                skipped.append(_name(sid))
                continue
            rows[_norm_id(sid)] = {"subnet_id": sid, "vnet_id": vnet_id or _vnet_of(sid),
                                   "used": used, "limit": limit, "pct": round(100.0 * used / limit, 1)}
    return rows, sorted(set(skipped))


def _analyze_utilization(rows, thresholds, findings):
    warn = float(thresholds["subnet_warn_pct"])
    crit = float(thresholds["subnet_crit_pct"])
    over = 0
    for key in sorted(rows):
        row = rows[key]
        if row["pct"] < warn:
            continue
        over += 1
        sid = row["subnet_id"]
        vnet = _name(row["vnet_id"])
        subnet = _name(sid)
        severity = "critical" if row["pct"] >= crit else "high"
        free = int(row["limit"] - row["used"])
        findings.append(_finding(
            f"CAP-SUBNET-UTIL:{vnet}:{subnet}", severity, sid,
            f"Subnet {vnet}/{subnet} is {row['pct']:g}% utilized ({int(row['used'])}/{int(row['limit'])} IPs)",
            {"currentValue": int(row["used"]), "limit": int(row["limit"]), "utilization_pct": row["pct"],
             "free": free, "warn_pct": warn, "crit_pct": crit},
            "New NICs, private endpoints, scale-out instances or service injections in this subnet will "
            "fail once it is full. Azure reserves 5 IPs in every subnet. Add an address prefix / larger "
            "subnet or move workloads to a new subnet.",
            _human([_usage_script(row["vnet_id"]),
                    f"az network vnet subnet show -g {_rg(sid)} --vnet-name {vnet} -n {subnet} "
                    "--query \"{prefix:addressPrefix,prefixes:addressPrefixes,delegations:delegations[].serviceName}\"",
                    "# Change (review before running):",
                    f"# az network vnet subnet update -g {_rg(sid)} --vnet-name {vnet} -n {subnet} "
                    "--address-prefixes <current-prefix> <additional-prefix>"]),
            [DOCS["vnet_usage"], DOCS["vnet_faq"], DOCS["cli_subnet"]]))
    return over


def _least_squares(points):
    """Slope (IPs/day) and intercept from [(day_ordinal, used)]; None if undefined."""

    n = len(points)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope = sxy / sxx
    return slope, mean_y - slope * mean_x


def _analyze_forecast(history, rows, as_of, thresholds, findings):
    horizon = int(thresholds["forecast_days"])
    series = {}
    for snap in history:
        sid = _norm_id(snap.get("subnet_id"))
        day = _date(snap.get("as_of"))
        used = _num(snap.get("used"))
        if not sid or day is None or used is None or day > as_of:
            continue
        series.setdefault(sid, {})[day.toordinal()] = used
    forecasts = 0
    for key in sorted(series):
        row = rows.get(key)
        if not row:
            continue
        points = dict(series[key])
        points[as_of.toordinal()] = row["used"]
        fit = _least_squares(sorted(points.items()))
        if fit is None:
            continue
        slope, _intercept = fit
        if slope <= 0 or row["used"] >= row["limit"]:
            continue
        days = (row["limit"] - row["used"]) / slope
        if days > horizon:
            continue
        days_ceil = max(1, math.ceil(days))
        projected = as_of + datetime.timedelta(days=days_ceil)
        forecasts += 1
        sid = row["subnet_id"]
        vnet = _name(row["vnet_id"])
        subnet = _name(sid)
        findings.append(_finding(
            f"CAP-SUBNET-FORECAST:{vnet}:{subnet}", "medium", sid,
            f"Subnet {vnet}/{subnet} projected to exhaust on {projected.isoformat()} ({days_ceil} days)",
            {"growth_ips_per_day": round(slope, 2), "currentValue": int(row["used"]), "limit": int(row["limit"]),
             "as_of": as_of.isoformat(), "projected_exhaustion": projected.isoformat(),
             "days_to_exhaustion": days_ceil, "samples": len(points), "forecast_days": horizon,
             "method": "least-squares linear fit of history + current usage"},
            "Linear growth from the usage history exhausts this subnet inside the forecast window. Plan an "
            "additional prefix or new subnet before the projected date.",
            _human([_usage_script(row["vnet_id"])]),
            [DOCS["vnet_usage"]]))
    return forecasts


def _analyze_special_subnets(vnets, findings):
    for vnet in sorted(vnets, key=lambda v: _norm_id(v.get("id"))):
        vid = _text(vnet.get("id"))
        vname = _text(vnet.get("name")) or _name(vid)
        subnets = [s for s in _props(vnet).get("subnets") or [] if isinstance(s, dict)]
        for subnet in sorted(subnets, key=lambda s: _text(s.get("name")).casefold()):
            sname = _text(subnet.get("name")) or _name(subnet.get("id"))
            rule = SPECIAL_SUBNETS.get(sname.casefold())
            if not rule:
                continue
            minimum, doc, why = rule
            nets = [n for n in (_ipv4(p) for p in _subnet_prefixes(subnet)) if n is not None]
            if not nets:
                continue
            largest = min(n.prefixlen for n in nets)
            if largest <= minimum:
                continue
            sid = _text(subnet.get("id")) or f"{vid}/subnets/{sname}"
            findings.append(_finding(
                f"CAP-SPECIAL-SUBNET-UNDERSIZED:{vname}:{sname}", "medium", sid,
                f"{sname} in {vname} is /{largest}; /{minimum} or larger is required/recommended",
                {"prefixes": [str(n) for n in nets], "required_min": f"/{minimum}", "rule": why},
                why + " Resize before deploying or scaling the service (the subnet may need to be "
                "empty, or an additional prefix added).",
                _human([f"az network vnet subnet show -g {_rg(vid)} --vnet-name {vname} -n {sname} "
                        "--query \"{prefix:addressPrefix,prefixes:addressPrefixes}\"",
                        "# Change (review before running):",
                        f"# az network vnet subnet update -g {_rg(vid)} --vnet-name {vname} -n {sname} "
                        f"--address-prefixes <new-/{minimum}-or-larger-prefix>"]),
                [DOCS[doc], DOCS["cli_subnet"]]))


def _largest_free_block(space, used):
    free = list(space)
    for sub in used:
        nxt = []
        for block in free:
            if sub.subnet_of(block):
                nxt.extend(block.address_exclude(sub))
            elif block.subnet_of(sub):
                continue
            else:
                nxt.append(block)
        free = nxt
    return min((b.prefixlen for b in free), default=None)


def _analyze_address_space(vnets, thresholds, findings):
    min_free = int(thresholds["vnet_min_free_prefix"])
    for vnet in sorted(vnets, key=lambda v: _norm_id(v.get("id"))):
        vid = _text(vnet.get("id"))
        vname = _text(vnet.get("name")) or _name(vid)
        p = _props(vnet)
        space = [n for n in (_ipv4(x) for x in (p.get("addressSpace") or {}).get("addressPrefixes") or [])
                 if n is not None]
        if not space:
            continue
        used = []
        for subnet in p.get("subnets") or []:
            if isinstance(subnet, dict):
                used.extend(n for n in (_ipv4(x) for x in _subnet_prefixes(subnet)) if n is not None)
        largest = _largest_free_block(sorted(set(space)), sorted(set(used)))
        if largest is not None and largest <= min_free:
            continue
        total = sum(n.num_addresses for n in space)
        allocated = sum(n.num_addresses for n in set(used))
        findings.append(_finding(
            f"CAP-VNET-SPACE-FULL:{vname}", "low", vid,
            f"VNet {vname} has no free block of /{min_free} or larger for new subnets",
            {"address_prefixes": [str(n) for n in space], "allocated_addresses": allocated,
             "total_addresses": total, "largest_free_prefix": f"/{largest}" if largest is not None else None,
             "min_free_prefix": f"/{min_free}"},
            "Every address prefix is allocated to subnets (the smallest supported IPv4 subnet is /29). "
            "Add a non-overlapping address prefix to the VNet (update peerings afterwards) before the "
            "next subnet is needed.",
            _human([f"az network vnet show -g {_rg(vid)} -n {vname} "
                    "--query \"{space:addressSpace.addressPrefixes,subnets:subnets[].addressPrefix}\"",
                    "# Change (review before running):",
                    f"# az network vnet update -g {_rg(vid)} -n {vname} "
                    "--address-prefixes <existing-prefixes> <new-prefix>"]),
            [DOCS["vnet_faq"], DOCS["cli_vnet"]]))


def _analyze_gateway_metrics(metrics, thresholds, findings):
    cpu_pct = float(thresholds["gateway_cpu_pct"])
    util_pct = float(thresholds["gateway_util_pct"])
    worst = {}
    for m in metrics:
        metric = _text(m.get("metric"))
        value = _num(m.get("value"))
        if value is None or metric not in CPU_METRICS + LIMIT_METRICS:
            continue
        dims = m.get("dimensions") if isinstance(m.get("dimensions"), dict) else {}
        dim_text = ",".join(f"{k}={_text(dims[k])}" for k in sorted(dims))
        if metric in CPU_METRICS:
            pct, limit, threshold = value, None, cpu_pct
        else:
            limit = _num(m.get("limit"))
            if not limit or limit <= 0:
                continue
            pct, threshold = 100.0 * value / limit, util_pct
        if pct < threshold:
            continue
        key = (_norm_id(m.get("resource_id")), metric, dim_text)
        if key not in worst or pct > worst[key][0]:
            worst[key] = (round(pct, 1), value, limit, threshold, _text(m.get("resource_id")), dims)
    for key in sorted(worst):
        pct, value, limit, threshold, rid, dims = worst[key]
        metric, dim_text = key[1], key[2]
        gname = _name(rid)
        er = metric.startswith(("ExpressRoute", "ScalableExpressRoute"))
        findings.append(_finding(
            f"CAP-GW-METRIC:{gname}:{metric}" + (f":{dim_text}" if dim_text else ""), "high", rid,
            f"Gateway {gname}: {metric} at {pct:g}% of capacity (threshold {threshold:g}%)",
            {"metric": metric, "value": value, "limit": limit, "utilization_pct": pct,
             "threshold_pct": threshold, "dimensions": dims},
            ("Sustained high ExpressRoute gateway CPU / throughput degrades forwarding; consider a larger "
             "gateway SKU or scale units and review flows and learned routes."
             if er else
             "The VPN gateway is near its configured capacity (limit = SKU benchmark you supplied). "
             "Consider a higher VPN gateway SKU or spreading tunnels."),
            _human([f"az monitor metrics list --resource {rid} --metric {metric} "
                    "--aggregation " + ("Maximum" if metric == "ExpressRouteGatewayCountOfRoutesLearnedFromPeer"
                                        else "Average") + " --interval PT5M",
                    f"az network vnet-gateway show -g {_rg(rid)} -n {gname} --query \"sku\""]),
            [DOCS["gw_metrics"], DOCS["er_metrics"] if er else DOCS["vpn_skus"]]))
    return len(worst)


def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update({k: v for k, v in (data.get("thresholds") or {}).items() if k in DEFAULT_THRESHOLDS})
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

    vnets = items("vnets", lambda v: v.get("id"))
    usages = items("usages", lambda u: u.get("vnet_id"))
    history = items("history", lambda h: h.get("subnet_id"))
    gw_metrics = items("gateway_metrics", lambda m: m.get("resource_id"))
    as_of = _date(data.get("as_of"))
    if data.get("as_of") is not None and as_of is None:
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)")

    if vnets is None:
        gaps.append("vnets not collected (az network vnet list); special-subnet sizing and address-space "
                    "headroom checks skipped.")
    if usages is None:
        gaps.append("usages not collected (az rest --method get --url "
                    "https://management.azure.com/<vnet-id>/usages?api-version=2026-01-01); "
                    "subnet utilization and forecast skipped.")

    rows, skipped = _usage_rows(usages or [])
    over = forecasts = 0
    if usages is not None:
        over = _analyze_utilization(rows, thresholds, findings)
        if vnets:
            covered = {_norm_id(u.get("vnet_id")) for u in usages}
            missing = sorted(_text(v.get("name")) or _name(v.get("id")) for v in vnets
                             if _norm_id(v.get("id")) not in covered)
            if missing:
                gaps.append("usages not collected for VNet(s) " + ", ".join(missing) + ".")
    if skipped:
        warnings.append("Subnet usage without a size (limit <= 0) was skipped for: " + ", ".join(skipped) + ".")
    if history:
        if as_of is None:
            gaps.append("history supplied but as_of missing; exhaustion forecast skipped "
                        "(as_of is the date the usages were collected).")
        elif usages is not None:
            forecasts = _analyze_forecast(history, rows, as_of, thresholds, findings)
    if vnets is not None:
        _analyze_special_subnets(vnets, findings)
        _analyze_address_space(vnets, thresholds, findings)
    gw_hot = _analyze_gateway_metrics(gw_metrics or [], thresholds, findings)

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")

    findings.sort(key=lambda f: (("critical", "high", "medium", "low", "info").index(f["severity"]),
                                 f["resource_id"].casefold(), f["id"]))
    kpis = {}
    if usages is not None:
        kpis["subnets_over_threshold"] = over
    peak = max((r["pct"] for r in rows.values()), default=None)
    warn = float(thresholds["subnet_warn_pct"])
    metric_rows = [
        {"label": "Subnets analyzed", "value": str(len(rows)),
         "detail": "subnets with usage (currentValue / limit)", "tone": "neutral"},
        {"label": f"Subnets >= {warn:g}% utilized", "value": str(over),
         "detail": f"critical at >= {float(thresholds['subnet_crit_pct']):g}%",
         "tone": "good" if usages is not None and over == 0 else ("neutral" if usages is None else "critical")},
        {"label": "Peak subnet utilization", "value": "n/a" if peak is None else f"{peak:g}%",
         "detail": "highest currentValue / limit", "tone": "neutral" if peak is None else
         ("critical" if peak >= float(thresholds["subnet_crit_pct"]) else
          "warning" if peak >= warn else "good")},
        {"label": "Forecast exhaustions", "value": str(forecasts),
         "detail": f"within {int(thresholds['forecast_days'])} days" if history and as_of
         else "history/as_of not provided",
         "tone": "neutral" if not (history and as_of) else ("good" if forecasts == 0 else "warning")},
        {"label": "Gateway metrics over threshold", "value": str(gw_hot),
         "detail": "verified gateway capacity metrics", "tone": "good" if gw_hot == 0 else "critical"},
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
