# Skill: Firewall Log Analysis

## Purpose

Parse, interpret, and analyze firewall logs across all 14 supported platforms. Identify security events, traffic anomalies, policy gaps, and operational issues from log data. Provide query templates and analysis patterns for common investigation scenarios.

---

## Log Formats

| Format | Used By | Structure |
|--------|---------|-----------|
| **Syslog (BSD/RFC 3164)** | Most on-prem firewalls, OPNsense, pfSense, VyOS, iptables | `<priority>timestamp hostname process[pid]: message` |
| **Syslog (IETF/RFC 5424)** | Modern syslog implementations | `<priority>version timestamp hostname app-name procid msgid SD message` |
| **CEF (Common Event Format)** | Check Point, Palo Alto (optional), ArcSight integration | `CEF:0|vendor|product|version|eventId|name|severity|extension` |
| **LEEF (Log Event Extended Format)** | Check Point (QRadar integration) | `LEEF:1.0|vendor|product|version|eventId|key=value pairs` |
| **JSON** | Azure Firewall, AWS Network Firewall, Zscaler NSS, REST APIs | Structured key-value JSON objects |
| **CSV / TSV** | PAN-OS (traffic/threat logs), FortiGate (FortiAnalyzer export) | Comma/tab-separated fields |
| **Custom** | Cisco ASA (syslog with ASA-x-xxxxxx message IDs), Sophos XG | Vendor-specific structured syslog |
| **pf log (filterlog)** | OPNsense, pfSense | CSV-style fields in syslog: `filterlog: rule,subrule,anchor,...,action,direction,ip-version,...` |

---

## Key Fields for Analysis

Every firewall log entry should be parsed for these critical fields:

| Field | Description | Analysis Value |
|-------|-------------|----------------|
| **Timestamp** | When the event occurred | Timeline correlation, burst detection |
| **Source IP** | Origin of the traffic | Identify attackers, anomalous internal hosts |
| **Source Port** | Origin port | Ephemeral vs well-known; scanning patterns |
| **Destination IP** | Target of the traffic | Identify targeted assets |
| **Destination Port** | Target port/service | Service identification, port scanning |
| **Protocol** | TCP, UDP, ICMP, etc. | Protocol anomalies |
| **Action** | Allow, deny, drop, reject, alert | Policy enforcement verification |
| **Rule Name/ID** | Which rule matched | Rule utilization, shadow rule detection |
| **Bytes/Packets** | Volume metrics | Data exfiltration, DDoS indicators |
| **Application** | App-ID or application name (L7 firewalls) | Shadow IT detection, application control verification |
| **Threat/IPS** | Threat name, severity, CVE | Security event triage |
| **NAT** | Pre/post-NAT addresses | Correlation, troubleshooting |
| **Session Duration** | How long the session lasted | Long-lived vs short-lived anomalies |
| **User** | User-ID (if integrated) | User attribution, compromised account detection |

---

## Common Analysis Patterns

### 1. Top Denied Flows
Identify the most frequently denied traffic — reveals misconfigured applications, scanning, or missing policy rules.

### 2. Geographic Anomalies
Traffic from/to unexpected countries — potential C&C, data exfiltration, or unauthorized access.

### 3. Port Scanning Detection
Single source hitting multiple destination ports or IPs in a short window.

### 4. Policy Gap Detection
Denied traffic that should have been allowed (user-reported issues) — candidate for new rules.

### 5. Unused Rule Detection
Rules with zero hits over the observation period — candidates for cleanup.

### 6. Data Exfiltration Indicators
Unusually high outbound bytes from internal hosts, especially to uncommon destinations.

### 7. Brute-Force Detection
Repeated denied connections to management ports (SSH/22, RDP/3389, HTTPS/443 management).

---

## Per-Vendor Log Queries

### Azure Firewall (KQL — Log Analytics)

```kql
// Top denied flows (structured logs)
AZFWNetworkRule
| where Action == "Deny"
| summarize DenyCount=count() by SourceIp, DestinationIp, DestinationPort, Protocol
| order by DenyCount desc
| take 20

// Application rule hits
AZFWApplicationRule
| where TimeGenerated > ago(24h)
| summarize HitCount=count() by Fqdn, Action
| order by HitCount desc

// Threat intelligence hits
AZFWThreatIntel
| where TimeGenerated > ago(7d)
| project TimeGenerated, SourceIp, DestinationIp, DestinationPort, ThreatDescription, Action

// IDPS signature alerts (Premium)
AZFWIdpsSignature
| where Severity in (1, 2)
| summarize AlertCount=count() by SignatureId, Description, Severity
| order by AlertCount desc
```

### AWS Network Firewall (CloudWatch Logs Insights)

```
# Top denied flows
fields @timestamp, event.src_ip, event.dest_ip, event.dest_port, event.event_type
| filter event.event_type = "drop"
| stats count() as DenyCount by event.src_ip, event.dest_ip, event.dest_port
| sort DenyCount desc
| limit 20

# Alert events
fields @timestamp, event.alert.signature, event.alert.severity, event.src_ip, event.dest_ip
| filter event.event_type = "alert"
| sort @timestamp desc
| limit 50
```

### GCP Cloud Firewall (Cloud Logging)

```
# Denied traffic
resource.type="gce_subnetwork"
jsonPayload.disposition="DENIED"
| ORDER BY timestamp DESC
| LIMIT 50

# Top denied source IPs (via Log Analytics or BigQuery export)
SELECT jsonPayload.connection.src_ip, COUNT(*) as deny_count
FROM `project.dataset.compute_googleapis_com_firewall`
WHERE jsonPayload.disposition = 'DENIED'
GROUP BY jsonPayload.connection.src_ip
ORDER BY deny_count DESC
LIMIT 20
```

### Palo Alto Networks (PAN-OS)

```bash
# CLI: Show traffic log (last 100 denied)
> show log traffic direction equal backward action equal deny last 100

# Panorama / Log query
( action eq deny ) and ( receive_time in last-24-hrs )
| sort by repeatcnt desc

# Threat log
> show log threat last 50
( severity geq high ) and ( receive_time in last-24-hrs )
```

### Fortinet FortiGate

```bash
# CLI: Show traffic log
FGT# execute log filter category 0
FGT# execute log filter field action deny
FGT# execute log display

# FortiAnalyzer SQL query
SELECT src, dst, dstport, action, COUNT(*) as cnt
FROM $log
WHERE action='deny' AND logtime > NOW() - INTERVAL 24 HOUR
GROUP BY src, dst, dstport, action
ORDER BY cnt DESC
LIMIT 20
```

### Check Point

```bash
# SmartLog query (SmartConsole)
action:Drop AND NOT service:domain-udp | last 24 hours

# CLI: fw log
fw log -c deny -n 100

# Log Exporter (JSON to SIEM)
cp_log_export name "siem_feed" target-server <siem-ip> target-port 514 protocol udp format json
```

### Cisco ASA

```bash
# Syslog message IDs for denied traffic
# ASA-4-106023: Deny <protocol> src <iface>:<ip>/<port> dst <iface>:<ip>/<port>
# ASA-2-106001: Inbound TCP connection denied

# Show denied connections
ASA# show logging | include 106023
ASA# show threat-detection statistics top access-list
```

### Juniper SRX

```bash
# Show security log (on-box)
> show log messages | match RT_FLOW_SESSION_DENY
> show security log | match DENY

# Structured syslog (stream mode)
set security log mode stream
set security log stream <name> host <siem-ip>
set security log stream <name> format sd-syslog   # structured data
```

### OPNsense

```bash
# filterlog format (parsed from /var/log/filter.log)
# Fields: rule-number,sub-rule,anchor,tracker,interface,reason,action,direction,...
# action field: pass or block

# View live log
clog /var/log/filter.log | grep ",block,"

# Syslog forwarding (System > Settings > Logging > Remote)
# Target: syslog server, UDP/TCP/TLS, facility local0-local7

# REST API: Fetch log entries
curl -u "<key>:<secret>" \
  "https://<opnsense>/api/diagnostics/firewall/log"
```

### pfSense

```bash
# filterlog format (same as OPNsense — pf-based)
# View live firewall log
clog /var/log/filter.log | grep ",block,"

# GUI: Status > System Logs > Firewall
# Filter by action, interface, source/dest

# Syslog forwarding: Status > System Logs > Settings > Remote Logging Options
# Enable remote syslog, set remote log server IP, select facilities
```

### VyOS

```bash
# Syslog configuration for firewall logs
set system syslog host <siem-ip> facility kern level info
set system syslog host <siem-ip> protocol udp

# Firewall log prefix (in rules)
set firewall name WAN-IN rule 99 log enable
set firewall name WAN-IN rule 99 log-prefix "[WAN-IN-DENY] "

# View firewall log
$ show log | grep "\[WAN-IN-DENY\]"

# Monitor live
$ monitor firewall name WAN-IN
```

### iptables / nftables

```bash
# LOG target with prefix
iptables -A INPUT -j LOG --log-prefix "[FW-INPUT-DROP] " --log-level 4
iptables -A FORWARD -j LOG --log-prefix "[FW-FORWARD-DROP] " --log-level 4

# View logs (depends on syslog config)
grep "\[FW-INPUT-DROP\]" /var/log/kern.log
journalctl -k | grep "FW-INPUT-DROP"

# nftables logging
nft add rule inet filter input log prefix \"[FW-INPUT-DROP] \" drop

# Parse iptables log fields:
# IN=eth0 OUT= SRC=1.2.3.4 DST=10.0.0.1 LEN=60 PROTO=TCP SPT=12345 DPT=22

# Rate-limit logging to avoid log flooding
iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "[FW-RATE] "
```

---

## Analysis Workflow

1. **Define the question** — what are you investigating? (security incident, policy validation, capacity planning, troubleshooting)
2. **Set the time window** — narrow to the relevant period.
3. **Query for relevant events** — use vendor-specific log queries above.
4. **Aggregate and summarize** — group by source, destination, port, action.
5. **Identify anomalies** — deviations from baseline traffic patterns.
6. **Correlate** — cross-reference with other data sources (DNS logs, endpoint logs, SIEM alerts).
7. **Report** — summarize findings with evidence (log excerpts, charts, top-N tables).

---
**Analysis only — verify against vendor documentation before applying.**
