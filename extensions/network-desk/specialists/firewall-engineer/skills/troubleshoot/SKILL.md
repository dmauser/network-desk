# Skill: Firewall Troubleshooting

## Purpose

Systematically diagnose and resolve firewall connectivity issues across all 14 supported platforms. Follow a structured packet-flow methodology to isolate whether the problem is in policy, NAT, routing, or the network path itself.

---

## Troubleshooting Methodology

Follow these steps in order — do not skip ahead:

```
1. IDENTIFY SYMPTOMS
   └─ What is failing? (connection timeout, reset, ICMP unreachable, partial connectivity)
   └─ Is it new traffic or existing sessions breaking?
   └─ When did it start? (correlate with change windows)

2. CHECK PACKET FLOW (Does the packet reach the firewall?)
   └─ Packet capture on ingress interface
   └─ Verify source routing / ARP resolution

3. VERIFY POLICY (Is the traffic permitted by a rule?)
   └─ Identify which rule matches (or if default deny hits)
   └─ Check for shadow rules intercepting the traffic

4. CHECK NAT (Is NAT translating correctly?)
   └─ Source NAT — verify post-NAT source IP
   └─ Destination NAT — verify pre-NAT vs post-NAT destination
   └─ NAT hairpin / loopback scenarios

5. VERIFY ROUTING (Is the return path correct?)
   └─ Check routing table on the firewall
   └─ Asymmetric routing — return traffic via a different path?

6. INSPECT SESSION TABLE (Is a session established?)
   └─ Session present? State? Timeout?
   └─ TCP state issues (SYN_SENT, half-open, etc.)

7. CHECK MTU / FRAGMENTATION
   └─ MSS clamping, PMTUD, tunnel overhead

8. VERIFY APPLICATION LAYER
   └─ L7 inspection blocking? (App-ID, IPS, URL filter, SSL inspection)
```

---

## Per-Vendor Diagnostic Commands

### Azure Firewall

```bash
# Check if traffic is being processed (Log Analytics / KQL)
AZFWNetworkRule
| where SourceIp == "10.1.2.5" and DestinationIp == "10.1.3.10"
| project TimeGenerated, Action, Rule, Protocol, DestinationPort

# Check DNAT rule hits
AZFWNatRule
| where DestinationIp == "<public-ip>"
| project TimeGenerated, SourceIp, TranslatedIp, TranslatedPort, Action

# Verify effective routes in spoke subnet (is UDR pointing to firewall?)
az network nic show-effective-route-table \
  --resource-group <rg> --name <nic-name> -o table

# Azure Firewall diagnostic logs
az monitor diagnostic-settings list --resource <firewall-resource-id>
```

### AWS Network Firewall

```bash
# Check flow logs (if enabled)
# CloudWatch Logs Insights:
fields @timestamp, event.src_ip, event.dest_ip, event.dest_port, event.event_type
| filter event.src_ip = "10.1.2.5" AND event.dest_ip = "10.1.3.10"
| sort @timestamp desc

# Verify route tables point to firewall endpoint
aws ec2 describe-route-tables --route-table-id <rtb-id>

# Check firewall endpoint status
aws network-firewall describe-firewall --firewall-name <name> \
  --query 'FirewallStatus.SyncStates'
```

### GCP Cloud Firewall

```bash
# Check firewall rule evaluation
gcloud compute firewall-rules list --filter="name~allow" --format=table

# Connectivity test (simulates packet flow)
gcloud network-management connectivity-tests create test-dmz-to-db \
  --source-instance=projects/<proj>/zones/<zone>/instances/<src-vm> \
  --destination-instance=projects/<proj>/zones/<zone>/instances/<dst-vm> \
  --protocol=TCP --destination-port=3306

# VPC flow logs
gcloud logging read 'resource.type="gce_subnetwork" AND jsonPayload.connection.src_ip="10.1.2.5"' \
  --limit=20
```

### Palo Alto Networks (PAN-OS)

```bash
# Test security policy match
> test security-policy-match source 10.1.2.5 destination 10.1.3.10 protocol 6 destination-port 3306 from DMZ to Database

# Packet capture (on dataplane)
> debug dataplane packet-diag set filter match source 10.1.2.5 destination 10.1.3.10
> debug dataplane packet-diag set capture stage receive file rx.pcap
> debug dataplane packet-diag set capture stage transmit file tx.pcap
> debug dataplane packet-diag set capture on

# Session table
> show session all filter source 10.1.2.5 destination 10.1.3.10

# Global counters (check for drops)
> show counter global filter severity drop delta yes
```

### Fortinet FortiGate

```bash
# Policy lookup
FGT# diagnose firewall iprope lookup <src-ip> <dst-ip> <proto> <dport>

# Sniffer (packet capture)
FGT# diagnose sniffer packet any "host 10.1.2.5 and host 10.1.3.10" 4 0 l

# Session table
FGT# diagnose sys session list | grep "10.1.2.5"

# Debug flow (shows policy evaluation in real-time)
FGT# diagnose debug flow filter addr 10.1.2.5
FGT# diagnose debug flow trace start 100
FGT# diagnose debug enable
# ... reproduce traffic ...
FGT# diagnose debug disable
```

### Check Point (R81+)

```bash
# fw monitor (packet capture at inspection points)
fw monitor -e "accept src=10.1.2.5 and dst=10.1.3.10;"

# fw ctl zdebug drop (show reason for drops)
fw ctl zdebug drop | grep "10.1.2.5"

# Connection table
fw tab -t connections -f -u | grep "10.1.2.5"

# Policy verification
mgmt_cli show access-rulebase name "Network" filter "src:10.1.2.5 AND dst:10.1.3.10" -f json
```

### Cisco ASA / FTD

```bash
# Packet tracer (simulates full packet path)
ASA# packet-tracer input dmz tcp 10.1.2.5 12345 10.1.3.10 3306

# Show connection table
ASA# show conn address 10.1.2.5

# Capture on interface
ASA# capture CAP1 interface dmz match tcp host 10.1.2.5 host 10.1.3.10 eq 3306
ASA# show capture CAP1

# Show NAT translations
ASA# show xlate | include 10.1.2.5

# ASP drop reasons
ASA# show asp drop
```

### Juniper SRX

```bash
# Policy match test
> show security match-policies from-zone DMZ to-zone Database source-ip 10.1.2.5 destination-ip 10.1.3.10 protocol tcp destination-port 3306

# Flow session table
> show security flow session source-prefix 10.1.2.5 destination-prefix 10.1.3.10

# Packet capture (datapath debugging)
> monitor traffic interface ge-0/0/1 matching "host 10.1.2.5 and host 10.1.3.10"

# Flow trace (debug)
> set security flow traceoptions file flow-trace
> set security flow traceoptions flag basic-datapath
> set security flow traceoptions packet-filter filter1 source-prefix 10.1.2.5
# ... reproduce traffic ...
> show log flow-trace
```

### Zscaler

```bash
# ZIA: Check if traffic is being forwarded to Zscaler
# In ZIA Admin Portal: Logs > Web Logs / Firewall Logs
# Filter by source IP: 10.1.2.5

# ZPA: Check connector status
# ZPA Admin Portal: Dashboard > Connector Status

# App Connector diagnostic commands (on connector host)
zpa-connector-health-check

# NSS feed for raw log analysis via SIEM
```

### Sophos XG / XGS

```bash
# Packet capture (device console)
console> tcpdump -i any host 10.1.2.5

# Connection tracking
console> conntrack -L | grep 10.1.2.5

# Log viewer: Monitor & Analyze > Log Viewer
# Filter: src=10.1.2.5 AND dst=10.1.3.10
```

### OPNsense

```bash
# Packet capture via GUI: Interfaces > Diagnostics > Packet Capture
# Or via CLI:
tcpdump -i em1 host 10.1.2.5 and host 10.1.3.10 -nn

# Show pf state table for specific connection
pfctl -ss | grep "10.1.2.5"

# Show loaded rules (verify rule exists and order)
pfctl -sr | head -50
pfctl -vsr   # verbose — includes labels, hit counts

# Check if packet matches a rule
pfctl -sr -v | grep -A2 "10.1.3.0/24"

# Show pf info (counters, drops)
pfctl -si

# Show interface statistics
pfctl -sI -i em1

# Check NAT rules
pfctl -sn
```

### pfSense

```bash
# Packet capture: Diagnostics > Packet Capture
# Or CLI:
tcpdump -i em0 host 10.1.2.5 and host 10.1.3.10 -nn

# Show loaded rules
pfctl -sr

# Show states
pfctl -ss | grep "10.1.2.5"

# Show pf counters
pfctl -si

# Show NAT rules
pfctl -sn

# Check filter log for drops
clog /var/log/filter.log | grep "10.1.2.5"

# Verify gateway status
netstat -rn
```

### VyOS

```bash
# Show firewall rules and counters
$ show firewall name DMZ-to-DB

# Monitor traffic on interface
$ monitor traffic interface eth1 filter "host 10.1.2.5 and host 10.1.3.10"

# Show connection tracking
$ show conntrack table ipv4 | grep "10.1.2.5"

# Show session table filtered
$ show conntrack table ipv4 | match "10.1.2.5.*10.1.3.10"

# Show firewall statistics for specific ruleset
$ show firewall name DMZ-to-DB statistics

# Verify routing
$ show ip route 10.1.3.0/24
```

### iptables / nftables

```bash
# Verbose rule listing with hit counts
iptables -L FORWARD -v -n --line-numbers
iptables -L INPUT -v -n --line-numbers

# Check specific rule match
iptables -C FORWARD -s 10.1.2.5 -d 10.1.3.10 -p tcp --dport 3306 -j ACCEPT

# TRACE target for packet path debugging
iptables -t raw -A PREROUTING -s 10.1.2.5 -d 10.1.3.10 -p tcp --dport 3306 -j TRACE
# View trace output:
journalctl -k | grep TRACE
# or
dmesg | grep TRACE

# Connection tracking state
conntrack -L -s 10.1.2.5 -d 10.1.3.10
conntrack -E   # live event monitor

# NAT translations
conntrack -L -n   # show NAT entries
iptables -t nat -L -v -n --line-numbers

# nftables equivalents
nft list chain inet filter forward
nft monitor trace    # after adding: nft add rule ... meta nftrace set 1
```

---

## Common Issues and Solutions

| Issue | Symptom | Investigation | Resolution |
|-------|---------|---------------|------------|
| **Asymmetric routing** | Intermittent drops, TCP RSTs | Session table shows half-open sessions; packet captures show traffic entering one interface but return traffic on another | Fix routing to ensure symmetric paths, or disable state checking on affected interfaces (last resort) |
| **MTU / PMTUD failure** | Large transfers fail, small packets work | Capture shows fragmented packets or ICMP "need to frag" being dropped | Set MSS clamping (`set tcp-mss-adjust`), allow ICMP type 3 code 4, reduce MTU |
| **NAT hairpin** | Internal hosts cannot reach public IP of internal server | DNAT works from outside but fails from inside (same zone) | Configure NAT hairpin / reflection / U-turn NAT; ensure source NAT is applied for same-zone DNAT traffic |
| **Implicit deny hit** | New traffic flow blocked with no matching explicit deny rule | Logs show default deny rule match | Add an explicit allow rule for the traffic flow |
| **Session timeout** | Long-lived connections drop after inactivity | Session table shows session aging out | Increase session timeout for the specific application; configure TCP keepalives on endpoints |
| **L7 inspection blocking** | HTTPS or app traffic blocked despite L4 allow rule | SSL decryption errors, App-ID mismatch, IPS signature match | Check security profiles, SSL decryption exceptions, application overrides |

---
**Analysis only — verify against vendor documentation before applying.**
