"""NetOps flow insights — pure, offline, deterministic.

Scores flow-log coverage (virtual network flow logs vs retiring NSG flow logs), Traffic Analytics
enablement and Traffic Analytics flow data (denied flows, MaliciousFlow, top talkers) from raw
read-only Azure responses that the agent already collected (RunAzCliReadCommands /
execute_kusto_query). Stdlib only: JSON in, JSON out, no I/O, no clock, no network. Never
executes or emits Azure writes; `remediation_script` values are read-only verification commands
or commented, human-run steps.

Input (every key optional; an ABSENT key means "not collected" and becomes an evidence gap,
an EMPTY list means "collected, nothing there")::

    {
      "managed_scopes": ["/subscriptions/<id>", ...] | null,   # from netops-managed-scope
      "vnets":     [<az network vnet list object>],
      "flow_logs": [<az network watcher flow-log list --location <region> object>],
                   # targetResourceId, enabled, retentionPolicy,
                   # flowAnalyticsConfiguration.networkWatcherFlowAnalyticsConfiguration
                   #   {enabled, workspaceResourceId, trafficAnalyticsInterval}
                   # scoped by targetResourceId (the flow log itself lives in NetworkWatcherRG)
      "flow_rows": [<NTANetAnalytics row from the SKILL.md KQL>],
                   # "Query": "flow_summary" (default) | "malicious"
                   # flow_summary: TargetResourceId, FlowType, SrcIp, DestIp, DestPort, L4Protocol,
                   #   AclGroup, AclRule, AllowedInFlows, AllowedOutFlows, DeniedInFlows,
                   #   DeniedOutFlows, BytesSrcToDest, BytesDestToSrc
                   # malicious: PublicIp, FlowDirection, plus the flow counters above
      "ip_details": [<NTAIpDetails row>],                         # optional threat enrichment
                   # Ip, FlowType, ThreatType, ThreatDescription, Location
      "thresholds": {"denied_flows": 100, "top_talkers": 3}
    }

Output: the NetOps result envelope (see netops-report-renderer/models.py). KPI:
`flow_log_coverage_pct` = in-scope VNets with an enabled virtual-network-level flow log.
"""

from __future__ import annotations

import json
import sys

SKILL = "netops-flow-insights"

DOCS = {
    "vnet_flow_logs": "https://learn.microsoft.com/azure/network-watcher/vnet-flow-logs-overview",
    "nsg_flow_logs": "https://learn.microsoft.com/azure/network-watcher/nsg-flow-logs-overview",
    "cli_flow_log": "https://learn.microsoft.com/cli/azure/network/watcher/flow-log",
    "flow_log_api": "https://learn.microsoft.com/rest/api/network-watcher/flow-logs/get",
    "nta_table": "https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntanetanalytics",
    "nta_ip": "https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntaipdetails",
    "ta_schema": "https://learn.microsoft.com/azure/network-watcher/traffic-analytics-schema",
}

DEFAULT_THRESHOLDS = {"denied_flows": 100, "top_talkers": 3}
NSG_RETIREMENT = "2027-09-30"

INPUT_KEYS = ("vnets", "flow_logs", "flow_rows", "ip_details")


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


def _num(value):
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_text(value))
    except ValueError:
        return 0.0


def _bool(value):
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in ("true", "1", "yes")


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


def _scope_filter(items, managed, id_getter, dropped, label):
    kept = []
    for item in items:
        if _in_scope(id_getter(item), managed):
            kept.append(item)
        else:
            dropped[label] = dropped.get(label, 0) + 1
    return kept


def _fmt(value):
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.1f}"


# --- flow log configuration ---------------------------------------------------------

def _target_kind(target):
    lowered = _norm_id(target)
    if "/providers/microsoft.network/networksecuritygroups/" in lowered:
        return "nsg"
    if "/subnets/" in lowered:
        return "subnet"
    if "/providers/microsoft.network/networkinterfaces/" in lowered:
        return "nic"
    if "/providers/microsoft.network/virtualnetworks/" in lowered:
        return "vnet"
    return "other"


def _ta(flow_log):
    cfg = _props(flow_log).get("flowAnalyticsConfiguration") or {}
    return (cfg.get("networkWatcherFlowAnalyticsConfiguration") or {}) if isinstance(cfg, dict) else {}


def _location(flow_log):
    return _text(flow_log.get("location")) or "<region>"


def _analyze_flow_logs(vnets, flow_logs, findings):
    by_target = {}
    for fl in flow_logs:
        by_target.setdefault(_norm_id(_props(fl).get("targetResourceId")), []).append(fl)

    for fl in sorted(flow_logs, key=lambda f: (_norm_id(_props(f).get("targetResourceId")), _norm_id(f.get("id")))):
        p = _props(fl)
        fid = _text(fl.get("id"))
        name = _text(fl.get("name")) or _name(fid)
        target = _text(p.get("targetResourceId"))
        kind = _target_kind(target)
        enabled = _bool(p.get("enabled"))
        loc = _location(fl)
        show = f"az network watcher flow-log show --location {loc} --name {name}"
        if not enabled:
            findings.append(_finding(
                f"FLOW-LOG-DISABLED:{name}", "low" if kind == "nsg" else "medium", target or fid,
                f"Flow log {name} on {kind.upper()} {_name(target)} is disabled",
                {"flow_log": fid, "targetResourceId": target, "target_type": kind, "enabled": False},
                "No flow records are being written for this target. Re-enable it (or, for an NSG flow "
                "log, replace it with a virtual network flow log).",
                _human([show,
                        "# Change (review before running):",
                        f"# az network watcher flow-log update --location {loc} --name {name} --enabled true"]),
                [DOCS["cli_flow_log"], DOCS["vnet_flow_logs"]]))
        if kind == "nsg":
            findings.append(_finding(
                f"FLOW-NSG-FLOWLOG-RETIRING:{name}", "medium" if enabled else "low", target or fid,
                f"NSG flow log {name} on {_name(target)} (NSG flow logs retire on {NSG_RETIREMENT})",
                {"flow_log": fid, "targetResourceId": target, "enabled": enabled,
                 "retirement_date": NSG_RETIREMENT,
                 "note": "New NSG flow logs can no longer be created; after retirement Azure deletes "
                         "existing NSG flow log resources and Traffic Analytics stops for them."},
                "Migrate to virtual network flow logs on the parent VNet (or subnet/NIC). Avoid enabling "
                "both on the same workload to prevent duplicate logging and cost.",
                _human([show,
                        "# Change (review before running):",
                        f"# az network watcher flow-log create --location {loc} --name <vnet-flow-log-name> "
                        "--vnet <vnet-id> --storage-account <storage-account-id> --workspace <workspace-id>"]),
                [DOCS["nsg_flow_logs"], DOCS["vnet_flow_logs"], DOCS["cli_flow_log"]]))
        ta = _ta(fl)
        if enabled and not _bool(ta.get("enabled")):
            findings.append(_finding(
                f"FLOW-TA-DISABLED:{name}", "low", target or fid,
                f"Traffic Analytics is not enabled on flow log {name}",
                {"flow_log": fid, "targetResourceId": target,
                 "networkWatcherFlowAnalyticsConfiguration": {
                     "enabled": _bool(ta.get("enabled")),
                     "workspaceResourceId": _text(ta.get("workspaceResourceId")) or None,
                     "trafficAnalyticsInterval": ta.get("trafficAnalyticsInterval")}},
                "Flow records only land in storage. Enable Traffic Analytics to a Log Analytics workspace "
                "so NTANetAnalytics can be queried (denied flows, top talkers, malicious flows).",
                _human([show,
                        "# Change (review before running):",
                        f"# az network watcher flow-log update --location {loc} --name {name} "
                        "--traffic-analytics true --workspace <workspace-id> --interval 10"]),
                [DOCS["cli_flow_log"], DOCS["flow_log_api"]]))

    covered = 0
    for vnet in sorted(vnets, key=lambda v: _norm_id(v.get("id"))):
        vid = _text(vnet.get("id"))
        vname = _text(vnet.get("name")) or _name(vid)
        own = by_target.get(_norm_id(vid), [])
        if any(_bool(_props(f).get("enabled")) for f in own):
            covered += 1
            continue
        if own:
            continue  # disabled VNet flow log already reported as FLOW-LOG-DISABLED
        prefix = _norm_id(vid) + "/subnets/"
        partial = sorted(_name(t) for t, fls in by_target.items()
                         if t.startswith(prefix) and any(_bool(_props(f).get("enabled")) for f in fls))
        loc = _text(vnet.get("location")) or "<region>"
        findings.append(_finding(
            f"FLOW-VNET-NO-FLOWLOG:{vname}", "medium", vid,
            f"VNet {vname} has no enabled virtual network flow log"
            + (" (subnet-level only: " + ", ".join(partial) + ")" if partial else ""),
            {"vnet": vid, "subnet_flow_logs": partial,
             "note": "Coverage counts an enabled flow log whose targetResourceId is the VNet."},
            "Without flow logs there is no record of allowed/denied traffic for incident triage. Enable a "
            "virtual network flow log (optionally with Traffic Analytics).",
            _human([f"az network watcher flow-log list --location {loc} "
                    f"--query \"[?targetResourceId=='{vid}']\"",
                    "# Change (review before running):",
                    f"# az network watcher flow-log create --location {loc} --name <flow-log-name> "
                    f"--vnet {vid} --storage-account <storage-account-id> --workspace <workspace-id>"]),
            [DOCS["vnet_flow_logs"], DOCS["cli_flow_log"]]))
    return covered, len(vnets)


# --- Traffic Analytics data ---------------------------------------------------------

def _denied(row):
    return _num(row.get("DeniedInFlows")) + _num(row.get("DeniedOutFlows"))


def _allowed(row):
    return _num(row.get("AllowedInFlows")) + _num(row.get("AllowedOutFlows"))


def _bytes(row):
    return _num(row.get("BytesSrcToDest")) + _num(row.get("BytesDestToSrc"))


def _analyze_denied(rows, thresholds, findings):
    limit = float(thresholds["denied_flows"])
    groups = {}
    for row in rows:
        denied = _denied(row)
        dest = _text(row.get("DestIp"))
        if denied <= 0 or not dest:
            continue
        key = (dest, _text(row.get("DestPort")), _text(row.get("L4Protocol")))
        g = groups.setdefault(key, {"denied": 0.0, "sources": {}, "rules": set(), "targets": set()})
        g["denied"] += denied
        src = _text(row.get("SrcIp")) or "<public/unknown>"
        g["sources"][src] = g["sources"].get(src, 0.0) + denied
        rule = "/".join(x for x in (_text(row.get("AclGroup")), _text(row.get("AclRule"))) if x)
        if rule:
            g["rules"].add(rule)
        if _text(row.get("TargetResourceId")):
            g["targets"].add(_text(row.get("TargetResourceId")))
    for key in sorted(groups):
        g = groups[key]
        if g["denied"] < limit:
            continue
        dest, port, proto = key
        targets = sorted(g["targets"])
        top_sources = sorted(g["sources"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        findings.append(_finding(
            f"FLOW-DENIED-HIGH:{dest}:{port or 'any'}/{proto or 'any'}", "medium",
            targets[0] if targets and targets[0].startswith("/") else "",
            f"{_fmt(g['denied'])} denied flows to {dest}:{port or '*'}/{proto or '*'}",
            {"denied_flows": g["denied"], "threshold": limit, "dest_ip": dest, "dest_port": port,
             "l4_protocol": proto, "top_sources": [{"src_ip": s, "denied_flows": c} for s, c in top_sources],
             "acl_rules": sorted(g["rules"]), "flow_targets": targets},
            "Investigate blocked traffic (possible SC-04 style deny): confirm whether the deny is intended. "
            "If legitimate traffic is being dropped, review the listed NSG / security admin rule with "
            "netops-nsg-firewall-audit; if unexpected sources, treat as scanning.",
            _human(["# KQL (Log Analytics):",
                    "NTANetAnalytics | where SubType == \"FlowLog\" "
                    f"| where DestIp == \"{dest}\"" + (f" and DestPort == {port}" if port.isdigit() else "")
                    + " | where DeniedInFlows > 0 or DeniedOutFlows > 0 "
                    "| summarize Denied = sum(DeniedInFlows + DeniedOutFlows) by SrcIp, AclGroup, AclRule "
                    "| order by Denied desc"]),
            [DOCS["nta_table"], DOCS["ta_schema"]]))


def _public_ip(row):
    ip = _text(row.get("PublicIp"))
    if ip:
        return ip
    for col in ("SrcPublicIps", "DestPublicIps"):
        raw = _text(row.get(col))
        if raw:
            return raw.split()[0].split("|")[0]
    return _text(row.get("SrcIp")) or _text(row.get("DestIp"))


def _analyze_malicious(rows, ip_details, findings):
    threat = {}
    for d in ip_details:
        if _text(d.get("FlowType")) == "MaliciousFlow" and _text(d.get("Ip")):
            threat.setdefault(_text(d.get("Ip")), {
                "ThreatType": _text(d.get("ThreatType")),
                "ThreatDescription": _text(d.get("ThreatDescription")),
                "Location": _text(d.get("Location"))})
    groups = {}
    for row in rows:
        if _text(row.get("FlowType")) != "MaliciousFlow":
            continue
        ip = _public_ip(row) or "<unknown>"
        g = groups.setdefault(ip, {"allowed": 0.0, "denied": 0.0, "targets": set(), "directions": set(),
                                   "dest": set()})
        g["allowed"] += _allowed(row)
        g["denied"] += _denied(row)
        if _text(row.get("TargetResourceId")):
            g["targets"].add(_text(row.get("TargetResourceId")))
        if _text(row.get("FlowDirection")):
            g["directions"].add(_text(row.get("FlowDirection")))
        port = _text(row.get("DestPort"))
        if port:
            g["dest"].add(port)
    for ip in sorted(groups):
        g = groups[ip]
        targets = sorted(g["targets"])
        findings.append(_finding(
            f"FLOW-MALICIOUS:{ip}", "high", targets[0] if targets and targets[0].startswith("/") else "",
            f"Traffic Analytics MaliciousFlow with {ip} ({_fmt(g['allowed'])} allowed, {_fmt(g['denied'])} denied)",
            {"public_ip": ip, "allowed_flows": g["allowed"], "denied_flows": g["denied"],
             "flow_directions": sorted(g["directions"]), "dest_ports": sorted(g["dest"]),
             "flow_targets": targets, "threat": threat.get(ip, {})},
            "Traffic Analytics classified flows with this IP as MaliciousFlow. Allowed flows mean the "
            "path is open: confirm with security operations, block the IP / tighten the rule and review "
            "the affected workloads.",
            _human(["# KQL (Log Analytics):",
                    f"NTAIpDetails | where Ip == \"{ip}\" "
                    "| project TimeGenerated, FlowType, ThreatType, ThreatDescription, Location, Url"]),
            [DOCS["nta_table"], DOCS["nta_ip"], DOCS["ta_schema"]]))
    return len(groups)


def _top_talkers(rows, count):
    pairs = {}
    for row in rows:
        src, dest = _text(row.get("SrcIp")), _text(row.get("DestIp"))
        if not src or not dest:
            continue
        pairs[(src, dest)] = pairs.get((src, dest), 0.0) + _bytes(row)
    ranked = sorted(((b, s, d) for (s, d), b in pairs.items() if b > 0), key=lambda t: (-t[0], t[1], t[2]))
    return ranked[:count]


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
    unattributed = [0]

    def items(key, id_getter, lenient=False):
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        rows = [v for v in value if isinstance(v, dict)]
        if lenient:
            # Traffic Analytics rows: only ARM-ID targets can be scope-checked.
            attributable = [r for r in rows if _text(id_getter(r)).startswith("/")]
            unattributed[0] += len(rows) - len(attributable)
            return [r for r in rows if not _text(id_getter(r)).startswith("/")] + \
                _scope_filter(attributable, managed, id_getter, dropped, key)
        return _scope_filter(rows, managed, id_getter, dropped, key)

    vnets = items("vnets", lambda v: v.get("id"))
    flow_logs = items("flow_logs", lambda f: _props(f).get("targetResourceId"))
    flow_rows = items("flow_rows", lambda r: r.get("TargetResourceId"), lenient=True)
    ip_details = data.get("ip_details")
    if ip_details is not None:
        if not isinstance(ip_details, list):
            raise ValueError("ip_details must be an array")
        ip_details = [d for d in ip_details if isinstance(d, dict)]

    if vnets is None:
        gaps.append("vnets not collected (az network vnet list); flow-log coverage KPI skipped.")
    if flow_logs is None:
        gaps.append("flow_logs not collected (az network watcher flow-log list --location <region> for each "
                    "region in scope); coverage and Traffic Analytics checks skipped.")
    if flow_rows is None:
        gaps.append("flow_rows not collected: Traffic Analytics data not queried (NTANetAnalytics KQL in "
                    "SKILL.md); denied-flow, malicious-flow and top-talker analysis skipped.")

    covered = total = 0
    if flow_logs is not None:
        covered, total = _analyze_flow_logs(vnets or [], flow_logs, findings)

    summary = [r for r in flow_rows or [] if _text(r.get("Query") or "flow_summary") != "malicious"]
    dedicated = [r for r in flow_rows or [] if _text(r.get("Query")) == "malicious"]
    malicious_rows = [r for r in (dedicated or summary) if _text(r.get("FlowType")) == "MaliciousFlow"]
    malicious = 0
    if flow_rows is not None:
        _analyze_denied(summary, thresholds, findings)
        malicious = _analyze_malicious(malicious_rows, ip_details or [], findings)

    for key, count in sorted(dropped.items()):
        warnings.append(f"{count} {key} item(s) outside the managed scope were excluded.")
    if unattributed[0] > 0 and managed is not None:
        warnings.append(f"{unattributed[0]} flow_rows item(s) had no ARM TargetResourceId and could not be "
                        "scope-checked; scope the KQL query to managed resources.")

    findings.sort(key=lambda f: (("critical", "high", "medium", "low", "info").index(f["severity"]),
                                 f["resource_id"].casefold(), f["id"]))
    kpis = {}
    coverage = _pct(covered, total) if vnets is not None and flow_logs is not None else None
    if coverage is not None:
        kpis["flow_log_coverage_pct"] = coverage
    denied_total = sum(_denied(r) for r in summary)
    allowed_total = sum(_allowed(r) for r in summary)
    talkers = _top_talkers(summary, int(thresholds["top_talkers"]))
    metric_rows = [
        {"label": "VNets with flow logs", "value": f"{covered}/{total}",
         "detail": "enabled virtual network flow log targeting the VNet",
         "tone": "neutral" if coverage is None else
                 ("good" if coverage >= 100 else "warning" if coverage >= 80 else "critical")},
        {"label": "Denied flows", "value": _fmt(denied_total) if flow_rows is not None else "n/a",
         "detail": "DeniedInFlows + DeniedOutFlows (NTANetAnalytics)", "tone": "neutral"},
        {"label": "Allowed flows", "value": _fmt(allowed_total) if flow_rows is not None else "n/a",
         "detail": "AllowedInFlows + AllowedOutFlows (NTANetAnalytics)", "tone": "neutral"},
        {"label": "Malicious flow IPs", "value": str(malicious) if flow_rows is not None else "n/a",
         "detail": "FlowType == MaliciousFlow",
         "tone": "neutral" if flow_rows is None else ("good" if malicious == 0 else "critical")},
    ]
    for rank, (total_bytes, src, dest) in enumerate(talkers, start=1):
        metric_rows.append({"label": f"Top talker #{rank}", "value": f"{src} -> {dest}",
                            "detail": f"{_fmt(total_bytes)} bytes (BytesSrcToDest + BytesDestToSrc)",
                            "tone": "neutral"})
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
