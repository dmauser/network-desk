# Skill: IPv6 Troubleshooting

## Purpose

Diagnose and resolve IPv6 connectivity, routing, DNS, firewall, and application issues across Azure, AWS, and GCP. Covers systematic troubleshooting methodology, common failure patterns, and cloud-specific diagnostic tools.

## Core Knowledge

### Troubleshooting Methodology

```
Layer 1-2: Link        → Interface up? IPv6 enabled? Link-local present?
Layer 3: Network       → IPv6 address assigned? Route to destination? PMTUD working?
Layer 3.5: ICMPv6      → NDP working? Router advertisements received? ICMPv6 not blocked?
Layer 4: Transport     → Firewall allows traffic? Correct port? TCP/UDP reachable?
Layer 7: Application   → App binding to IPv6? DNS returning AAAA? Correct address family?
```

### Common IPv6 Connectivity Issues

| Symptom | Likely Cause | Quick Check |
|---------|-------------|-------------|
| No IPv6 address | SLAAC/DHCPv6 failure, IPv6 disabled | `ip -6 addr show` |
| Can ping link-local but not GUA | Missing route or RA | `ip -6 route show` |
| Can ping GUA but not internet | Missing default route or firewall | `traceroute6 2600::` |
| Intermittent connectivity | PMTUD failure (ICMPv6 blocked) | `ping6 -s 1452 -M do <dest>` |
| DNS resolves but can't connect | Firewall rule missing for IPv6 | Check NSG/SG rules |
| Works on IPv4 not IPv6 | App only binding IPv4, missing rules | `ss -6 -tlnp` |
| Slow IPv6 | Suboptimal routing, tunneling | `traceroute6`, check path |

### Verifying IPv6 Reachability

```bash
# === Basic Connectivity ===

# Linux
ping6 -c 4 2001:db8::1                    # ICMPv6 echo
ping6 -c 4 -I eth0 fe80::1                # Link-local (specify interface)
traceroute6 2001:4860:4860::8888           # Trace IPv6 path
curl -6 https://ipv6.google.com            # HTTP over IPv6
curl -6 -v https://[2001:db8::1]:443       # Explicit IPv6 with port

# Windows
ping -6 2001:db8::1
tracert -6 2001:db8::1
Test-NetConnection -ComputerName 2001:db8::1 -Port 443
Resolve-DnsName www.example.com -Type AAAA

# macOS
ping6 2001:db8::1
traceroute6 2001:db8::1

# === Verify address and routes ===
ip -6 addr show                            # All IPv6 addresses
ip -6 addr show scope global               # Only GUA addresses
ip -6 route show                           # IPv6 routing table
ip -6 route get 2001:4860:4860::8888       # Which route is used?
ip -6 neigh show                           # IPv6 neighbor cache (NDP)

# Windows equivalents
Get-NetIPAddress -AddressFamily IPv6
Get-NetRoute -AddressFamily IPv6
Get-NetNeighbor -AddressFamily IPv6
```

### ICMPv6 Requirements — Don't Block It!

**Critical:** Unlike IPv4 where ICMP is often filtered, ICMPv6 is REQUIRED for basic IPv6 operation.

**Must-allow ICMPv6 types:**

| Type | Code | Name | Purpose |
|------|------|------|---------|
| 1 | 0 | Destination Unreachable | Error signaling |
| 2 | 0 | Packet Too Big | Path MTU Discovery (CRITICAL) |
| 3 | 0-1 | Time Exceeded | Traceroute, loop detection |
| 128 | 0 | Echo Request | Ping |
| 129 | 0 | Echo Reply | Ping response |
| 133 | 0 | Router Solicitation | Host discovers routers |
| 134 | 0 | Router Advertisement | Router announces prefixes |
| 135 | 0 | Neighbor Solicitation | ARP equivalent for IPv6 |
| 136 | 0 | Neighbor Advertisement | ARP reply equivalent |
| 137 | 0 | Redirect | Optimal path notification |

**Minimum Required for Functionality:**
```bash
# At minimum, NEVER block these (breaks basic connectivity):
# - Type 2 (Packet Too Big) — breaks PMTUD → black hole
# - Type 135/136 (NS/NA) — breaks NDP → no communication
# - Type 133/134 (RS/RA) — breaks SLAAC → no addresses

# Azure NSG: Allow essential ICMPv6
az network nsg rule create --resource-group myRG --nsg-name myNSG \
  --name AllowICMPv6Essential --priority 100 --direction Inbound \
  --protocol Icmp --access Allow --source-address-prefixes '*' \
  --destination-address-prefixes '*'

# AWS Security Group: ICMPv6 (all types)
aws ec2 authorize-security-group-ingress --group-id sg-xxx \
  --ip-permissions '[{"IpProtocol":"icmpv6","FromPort":-1,"ToPort":-1,"Ipv6Ranges":[{"CidrIpv6":"::/0"}]}]'

# GCP: Allow ICMPv6
gcloud compute firewall-rules create allow-icmpv6 \
  --network=my-vpc --allow=58 --source-ranges="::/0" --direction=INGRESS
```

### Path MTU Discovery for IPv6

**Key Difference from IPv4:** IPv6 routers NEVER fragment packets. Only the source can fragment. PMTUD is mandatory.

```
Source (MTU 1500) → Router (MTU 1280 link) → Destination
                         │
                         ├── Drops oversized packet
                         └── Sends ICMPv6 Type 2 "Packet Too Big" (MTU=1280)
                                    │
Source receives PTB ◄───────────────┘
Source reduces MSS to fit 1280 MTU
```

**Diagnosing PMTUD Issues:**
```bash
# Test with large packets (don't fragment flag)
ping6 -s 1452 -M do 2001:db8::1    # Linux: 1452 + 48 headers = 1500
ping -6 -l 1452 -f 2001:db8::1     # Windows: -f = don't fragment

# If this fails but small pings work → PMTUD broken (ICMPv6 Type 2 blocked)

# Check cached PMTU
ip -6 route show cache | grep mtu

# Reduce MSS as workaround (temporary!)
# On Linux firewall/router:
ip6tables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
  -j TCPMSS --set-mss 1220

# Cloud environments: check MTU settings
# Azure: Default MTU 1500, can go to 9000 (jumbo) within VNet
# AWS: Default 9001 in VPC, 1500 to internet
# GCP: Default 1460 (due to encapsulation), configurable per-network
```

### Neighbor Discovery Protocol (NDP) Issues

NDP replaces ARP in IPv6. Issues manifest as inability to communicate on the local link.

```bash
# Check NDP table (neighbor cache)
ip -6 neigh show
# States: REACHABLE, STALE, DELAY, PROBE, FAILED, INCOMPLETE

# Watch NDP activity
tcpdump -i eth0 -nn icmp6 and '(ip6[40] == 135 or ip6[40] == 136)'

# Symptoms of NDP failure:
# - Neighbor state stuck in INCOMPLETE or FAILED
# - Can't reach hosts on same subnet
# - Link-local pings fail

# Common causes:
# 1. ICMPv6 blocked by firewall (types 135/136)
# 2. Network filtering multicast (NDP uses multicast)
# 3. DAD (Duplicate Address Detection) failing
# 4. Too many entries causing neighbor cache overflow

# Azure-specific: Azure networking handles NDP at the platform level
# VM-to-VM on same subnet works via Azure's virtual switching
# You may not see traditional NDP behavior in packet captures

# Force NDP refresh
ip -6 neigh flush all
```

### DNS Resolution Issues

```bash
# === Diagnosing DNS ===

# Check if AAAA record exists
dig AAAA www.example.com +short
dig AAAA www.example.com @8.8.8.8        # Query specific resolver
nslookup -type=AAAA www.example.com

# Check both A and AAAA
dig www.example.com A +short
dig www.example.com AAAA +short

# Verify resolver supports IPv6 transport
dig @2001:4860:4860::8888 www.example.com AAAA  # Query over IPv6

# Check resolution order (nsswitch)
cat /etc/nsswitch.conf | grep hosts
# hosts: files dns → uses /etc/hosts first, then DNS

# Test Happy Eyeballs behavior
curl -v https://www.example.com 2>&1 | grep "Connected to"
# Shows which protocol was actually used

# === Common DNS Issues ===

# Problem: AAAA exists but IPv6 unreachable → client experiences timeout
# Solution: Remove AAAA or fix IPv6 path; Happy Eyeballs mitigates but adds latency

# Problem: DNS64 not synthesizing
# Check: Is the DNS64 resolver actually being used?
cat /etc/resolv.conf
# Verify resolver is the DNS64-enabled one, not a generic resolver

# Problem: /etc/hosts has IPv4 entry, overrides DNS
grep example.com /etc/hosts

# Problem: Stale AAAA record pointing to old address
dig AAAA www.example.com +trace  # Follow delegation chain
```

### Firewall/NSG Misconfigurations

**Pattern: IPv4 rules exist, IPv6 rules missing**

```bash
# === Azure NSG Audit ===
# List all rules and check for IPv6 coverage
az network nsg rule list --resource-group myRG --nsg-name myNSG -o table

# Common gap: Rule allows 0.0.0.0/0 but not ::/0
# Fix: Add matching rule with IPv6 source/destination

# Check effective rules on a NIC (includes NSG + Azure defaults)
az network nic list-effective-nsg --resource-group myRG --name myNIC

# === AWS Security Group Audit ===
aws ec2 describe-security-groups --group-ids sg-xxx \
  --query "SecurityGroups[0].{Ingress:IpPermissions,Egress:IpPermissionsEgress}" \
  --output json

# Look for rules with IpRanges (IPv4) but missing Ipv6Ranges
# Each rule needs both:
#   "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
#   "Ipv6Ranges": [{"CidrIpv6": "::/0"}]

# === GCP Firewall Audit ===
gcloud compute firewall-rules list --format="table(name,direction,sourceRanges,allowed)"

# Check if rules specify only IPv4 ranges (10.0.0.0/8)
# without corresponding IPv6 ranges

# === iptables/ip6tables (Linux hosts) ===
iptables -L -n -v    # IPv4 rules
ip6tables -L -n -v   # IPv6 rules — often empty or DEFAULT DROP!

# Common mistake: Hardened IPv4 (iptables) but no ip6tables rules
# Result: All IPv6 traffic allowed (no firewall) OR all blocked (default DROP)
```

### Application Not Binding to IPv6

```bash
# Check what addresses an application is listening on
ss -6 -tlnp                              # IPv6 TCP listeners
ss -tlnp | grep -E '::|\*'              # All listeners (look for :: or *)
netstat -tlnp | grep -E '::|\*'         # Alternative

# Expected: Application shows [::]:80 or :::80
# Problem:  Application shows 0.0.0.0:80 only (IPv4-only binding)

# === Common Application Fixes ===

# Nginx: Listen on both
# /etc/nginx/sites-available/default
# listen 80;
# listen [::]:80;            # Add this line

# Apache: Listen directive
# Listen [::]:80             # Binds dual-stack on most systems

# Node.js: Bind to '::'
# server.listen(3000, '::')  # Dual-stack
# NOT server.listen(3000, '0.0.0.0')  # IPv4 only

# Python Flask
# app.run(host='::', port=5000)  # Dual-stack

# Java: System property
# -Djava.net.preferIPv4Stack=false
# -Djava.net.preferIPv6Addresses=true

# Docker: Ensure container networking supports IPv6
# /etc/docker/daemon.json:
# {"ipv6": true, "fixed-cidr-v6": "fd00::/80"}

# Kubernetes: Pod must be in dual-stack cluster
# spec.ipFamilies: ["IPv4", "IPv6"]
# spec.ipFamilyPolicy: PreferDualStack
```

## Cloud-Specific Troubleshooting Tools

### Azure

```bash
# Network Watcher — IP Flow Verify (check if traffic allowed)
az network watcher test-ip-flow \
  --resource-group myRG \
  --vm myVM \
  --direction Inbound \
  --protocol TCP \
  --local "2001:db8::10:*" \
  --remote "2001:db8::20:443"

# Network Watcher — Next Hop
az network watcher show-next-hop \
  --resource-group myRG \
  --vm myVM \
  --source-ip "2001:db8::10" \
  --dest-ip "2001:db8::20"

# Connection Monitor (test IPv6 endpoint)
az network watcher connection-monitor create \
  --name ipv6-monitor \
  --endpoint-source-name myVM \
  --endpoint-source-resource-id /subscriptions/.../myVM \
  --endpoint-dest-name ipv6-target \
  --endpoint-dest-address "2001:db8::20" \
  --test-config-name tcp443 \
  --test-config-protocol Tcp \
  --test-config-tcp-port 443

# Effective Routes (see IPv6 routes)
az network nic show-effective-route-table \
  --resource-group myRG --name myNIC -o table

# NSG Flow Logs — include IPv6 traffic
# Ensure flow log version 2 captures IPv6
az network watcher flow-log create \
  --resource-group myRG --name myFlowLog \
  --nsg myNSG --storage-account myStorage \
  --log-version 2 --traffic-analytics true
```

### AWS

```bash
# VPC Reachability Analyzer (check IPv6 paths)
aws ec2 create-network-insights-path \
  --source eni-source-xxx \
  --destination eni-dest-xxx \
  --protocol tcp \
  --destination-port 443 \
  --filter-at-source '{"SourceAddress":"2001:db8::10"}' \
  --filter-at-destination '{"DestinationAddress":"2001:db8::20"}'

# Start analysis
aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-xxx

# Get results
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-xxx

# VPC Flow Logs — IPv6 traffic
# Flow log format includes srcaddr/dstaddr which shows IPv6
# Custom format to see IPv6 clearly:
aws ec2 create-flow-logs \
  --resource-type VPC --resource-ids vpc-xxx \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name ipv6-flow-logs \
  --log-format '${version} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${srcport} ${dstport} ${protocol} ${packets} ${bytes} ${start} ${end} ${action} ${log-status} ${type} ${pkt-src-addr} ${pkt-dst-addr}'

# Check route table for IPv6
aws ec2 describe-route-tables --route-table-ids rtb-xxx \
  --query "RouteTables[0].Routes[?DestinationIpv6CidrBlock]"

# Security Group — verify IPv6 rules exist
aws ec2 describe-security-groups --group-ids sg-xxx \
  --query "SecurityGroups[0].IpPermissions[*].Ipv6Ranges"
```

### GCP

```bash
# Connectivity Test (supports IPv6)
gcloud network-management connectivity-tests create ipv6-test \
  --source-instance=projects/myproj/zones/us-central1-a/instances/vm1 \
  --destination-ip-address=2001:db8::20 \
  --destination-port=443 \
  --protocol=TCP

# Get test results
gcloud network-management connectivity-tests describe ipv6-test

# Firewall Rules Log — check IPv6 hits
gcloud logging read 'resource.type="gce_subnetwork" AND
  jsonPayload.rule_details.direction="INGRESS" AND
  jsonPayload.connection.src_ip=~":" ' \
  --limit=50

# VPC Flow Logs — IPv6 entries
gcloud logging read 'resource.type="gce_subnetwork" AND
  logName="projects/myproj/logs/compute.googleapis.com%2Fvpc_flows" AND
  jsonPayload.connection.src_ip=~":"' \
  --limit=20 --format=json

# Check routes for IPv6
gcloud compute routes list --filter="destRange='::/0'"

# Packet Mirroring (full capture for IPv6 debug)
gcloud compute packet-mirrorings create ipv6-mirror \
  --region=us-central1 \
  --network=my-vpc \
  --collector-ilb=my-mirror-lb \
  --mirrored-instances=zones/us-central1-a/instances/vm1
```

## Flow Log Analysis for IPv6 Traffic

### Identifying IPv6 Issues in Flow Logs

```bash
# AWS — Find rejected IPv6 traffic (CloudWatch Logs Insights)
# Query:
# filter @message like /REJECT/
# | filter srcaddr like /:/
# | stats count(*) as rejections by srcaddr, dstaddr, dstport
# | sort rejections desc

# Azure — Log Analytics KQL for IPv6 flow analysis
# AzureNetworkAnalytics_CL
# | where FlowType_s == "ExternalPublic" or FlowType_s == "IntraVNet"
# | where SrcIP_s contains ":"
# | where FlowStatus_s == "D"  // Denied
# | summarize count() by SrcIP_s, DestIP_s, DestPort_d
# | order by count_ desc

# GCP — BigQuery for VPC flow logs
# SELECT
#   jsonPayload.connection.src_ip,
#   jsonPayload.connection.dest_ip,
#   jsonPayload.connection.dest_port,
#   jsonPayload.disposition
# FROM `project.dataset.vpc_flows`
# WHERE jsonPayload.connection.src_ip LIKE '%:%'
#   AND jsonPayload.disposition = 'DENIED'
# GROUP BY 1,2,3,4
# ORDER BY COUNT(*) DESC
```

### Systematic Debug Checklist

```bash
# Step 1: Verify IPv6 is enabled and address is assigned
ip -6 addr show scope global
# Expected: At least one GUA (2xxx: prefix) on the relevant interface

# Step 2: Check default route exists
ip -6 route show default
# Expected: default via <gateway> dev <interface>

# Step 3: Verify link-local connectivity (NDP working)
ping6 -c 2 fe80::1%eth0
# If fails: NDP/ICMPv6 issue at L2

# Step 4: Check gateway reachability
ping6 -c 2 <default_gateway_ipv6>
# If fails: Gateway down or wrong route

# Step 5: Test internet reachability
ping6 -c 2 2001:4860:4860::8888  # Google DNS
# If fails: Routing beyond gateway broken, check cloud routes

# Step 6: Test DNS resolution
dig AAAA www.google.com
# If fails: DNS resolver not supporting IPv6 queries

# Step 7: Test application port
curl -6 -v https://[2001:db8::1]:443
# If fails: App not listening on IPv6 or firewall blocking

# Step 8: Check firewall
# (Cloud NSG/SG + host firewall)
ip6tables -L -n -v | grep -i drop
az network watcher test-ip-flow ...
```

## Troubleshooting Tips

- **"Network unreachable" on IPv6?** Missing default route. Check `ip -6 route` and cloud route tables.
- **Packet Too Big never received?** ICMPv6 Type 2 blocked somewhere. Audit all firewalls in the path.
- **NDP flooding?** Possible ND spoofing or scanning. Enable RA Guard if supported.
- **IPv6 works locally but not across peering?** Check peering supports IPv6 and route tables propagate IPv6 prefixes.
- **curl hangs on IPv6 but works on IPv4?** Happy Eyeballs timeout. Fix IPv6 path or remove AAAA record.
- **Cloud VM has no IPv6?** Verify subnet is dual-stack, NIC has IPv6 config, and OS hasn't disabled IPv6.
- **Traceroute6 shows asterisks?** Intermediate hops may not respond to ICMPv6 (not necessarily a problem).
- **Duplicate Address Detected (DAD) failure?** Another host on the same subnet has the same IPv6 address. Check for conflicts.

---

**Analysis only — verify against vendor documentation before applying.**
