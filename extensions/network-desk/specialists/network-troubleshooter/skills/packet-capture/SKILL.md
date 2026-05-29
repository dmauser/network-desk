# Skill: Packet Capture and Analysis (ntsh_packet-capture)

Capture and analyze network packets using cloud-native tools and traditional utilities. This skill covers Azure Network Watcher packet capture, tcpdump, Wireshark filters, and analysis techniques for TLS handshakes and retransmissions.

---

## Azure Network Watcher Packet Capture

### Creating a Capture
```bash
# Start packet capture on a VM NIC — save to storage account
az network watcher packet-capture create \
  --name MyCapture \
  --vm MyVM \
  --resource-group MyRG \
  --storage-account mystorageaccount \
  --time-limit 300 \
  --filters '[
    {"protocol": "TCP", "remoteIPAddress": "10.0.2.5", "remotePort": "443"},
    {"protocol": "ICMP"}
  ]'

# Check capture status
az network watcher packet-capture show \
  --name MyCapture --location eastus

# Stop capture
az network watcher packet-capture stop \
  --name MyCapture --location eastus

# Download capture file from storage account
az storage blob download \
  --container-name network-watcher-logs \
  --name "subscriptions/.../packetCaptures/MyCapture.cap" \
  --file ./MyCapture.cap \
  --account-name mystorageaccount
```

### Capture Limits
- Maximum duration: 5 hours (18,000 seconds).
- Maximum file size: 1 GB per capture session.
- Maximum bytes per packet: configurable (default captures full packet; use smaller value to reduce file size).
- Filter limit: 5 filters per capture session.
- Requires Network Watcher Agent VM extension installed.

### Continuous Packet Capture (preview)
- Use standard packet capture for bounded, targeted captures; use Continuous packet capture only when you need a longer-running ring buffer for intermittent issues.
- Preview limits and regional support can change; currently frame it as a ring-buffer capture with a maximum capture window of up to 7 days and configurable file controls.
- Confirm storage account capacity, retention, and access controls before enabling continuous capture on busy NICs.

### Filter Syntax
```json
[
  {"protocol": "TCP", "localIPAddress": "10.0.1.4", "localPort": "443"},
  {"protocol": "TCP", "remoteIPAddress": "192.168.1.0/24", "remotePort": "1024-65535"},
  {"protocol": "UDP", "localPort": "53"},
  {"protocol": "ICMP"}
]
```

---

## tcpdump — Linux Packet Capture

### Common Capture Commands
```bash
# Capture all traffic on eth0, write to file
sudo tcpdump -i eth0 -w capture.pcap

# Capture traffic to/from specific host on port 443
sudo tcpdump -i eth0 host 10.0.2.5 and port 443 -w tls_capture.pcap

# Capture with packet count limit (prevent huge files)
sudo tcpdump -i eth0 -c 10000 -w limited_capture.pcap

# Capture full packets (no truncation — default may truncate)
sudo tcpdump -i eth0 -s 0 -w full_capture.pcap

# Capture only SYN packets (connection attempts)
sudo tcpdump -i eth0 'tcp[tcpflags] & (tcp-syn) != 0' -w syn_capture.pcap

# Capture only RST packets (connection resets)
sudo tcpdump -i eth0 'tcp[tcpflags] & (tcp-rst) != 0' -w rst_capture.pcap

# Capture DNS traffic (UDP and TCP port 53)
sudo tcpdump -i eth0 port 53 -w dns_capture.pcap

# Live display with human-readable output (for quick debugging)
sudo tcpdump -i eth0 host 10.0.2.5 and port 443 -nn -v
```

### Advanced Filters
```bash
# Traffic between two specific hosts
sudo tcpdump -i eth0 'host 10.0.1.4 and host 10.0.2.5'

# Traffic from a subnet
sudo tcpdump -i eth0 'src net 10.0.1.0/24 and dst port 443'

# Exclude SSH (useful when capturing over SSH connection)
sudo tcpdump -i eth0 'not port 22' -w capture.pcap

# ICMP only (ping, unreachable, etc.)
sudo tcpdump -i eth0 icmp -w icmp_capture.pcap

# Capture on specific VLAN
sudo tcpdump -i eth0.100 -w vlan100_capture.pcap
```

---

## Wireshark Display Filters

### Connection Analysis
```
# All TCP retransmissions — indicates packet loss or congestion
tcp.analysis.retransmission

# TCP zero window — receiver buffer full (application not reading fast enough)
tcp.analysis.zero_window

# TCP RST packets — connection resets
tcp.flags.reset == 1

# TCP SYN without SYN-ACK response — connection attempts that fail
tcp.flags.syn == 1 && tcp.flags.ack == 0

# Duplicate ACKs — receiver requesting retransmission
tcp.analysis.duplicate_ack

# TCP window full — sender limited by receiver window
tcp.analysis.window_full

# Out-of-order packets
tcp.analysis.out_of_order
```

### TLS/SSL Analysis
```
# TLS Client Hello — shows SNI, supported cipher suites, TLS version
tls.handshake.type == 1

# TLS Server Hello — shows selected cipher suite, TLS version
tls.handshake.type == 2

# TLS Certificate — server certificate in handshake
tls.handshake.type == 11

# TLS Alert messages — handshake failures, certificate errors
tls.alert_message

# TLS version filter
tls.record.version == 0x0303    # TLS 1.2
tls.record.version == 0x0304    # TLS 1.3

# Failed TLS handshakes (Alert after Client Hello)
tls.alert_message.level == 2    # Fatal alerts
```

### Protocol-Specific Filters
```
# DNS errors
dns.flags.rcode != 0

# DNS NXDOMAIN responses
dns.flags.rcode == 3

# HTTP response codes (unencrypted traffic)
http.response.code >= 400

# ICMP destination unreachable
icmp.type == 3

# ICMP need to fragment (MTU issues)
icmp.type == 3 && icmp.code == 4
```

---

## Capture at Strategic Points

### Where to Capture

**At the source VM NIC**: Captures traffic as the application sends it. If packets are present here but not at the destination, the drop is in the network path (NSG, route, firewall).

**At the firewall/NVA**: Capture on both ingress and egress interfaces. If traffic arrives but doesn't leave, the firewall policy is blocking. Use firewall-native logging (Azure Firewall diagnostics, NVA syslogs) when direct packet capture isn't available.

**At the load balancer**: Most cloud LBs don't support direct packet capture. Instead, capture at a backend instance and look for traffic from the LB's internal IP (Azure LB health probe source: 168.63.129.16; AWS NLB preserves client IP; ALB uses its own IP).

**At the destination VM NIC**: Confirms traffic arrives at the destination. If traffic is here but the application doesn't respond, the issue is at the OS/application layer (firewall, application not listening, application error).

### Dual-Point Capture Analysis
Capture simultaneously at source and destination. Compare:
1. Packet present at source but absent at destination → dropped in transit.
2. Packet present at both but response absent at source → return path blocked.
3. SYN at source, SYN-ACK at destination, but SYN-ACK never reaches source → asymmetric routing or return path NSG.

---

## Analyzing TLS Handshake Failures

### Full TLS 1.2 Handshake Flow
```
Client → Server: ClientHello (TLS version, cipher suites, SNI, extensions)
Server → Client: ServerHello (selected cipher, session ID)
Server → Client: Certificate (server's X.509 certificate chain)
Server → Client: ServerKeyExchange (DH parameters, if applicable)
Server → Client: ServerHelloDone
Client → Server: ClientKeyExchange (pre-master secret / DH public key)
Client → Server: ChangeCipherSpec
Client → Server: Finished (encrypted)
Server → Client: ChangeCipherSpec
Server → Client: Finished (encrypted)
```

### Common Failure Points
- **No ServerHello response**: Server doesn't support any of the client's proposed cipher suites or TLS versions.
- **Certificate error (Alert 42: bad_certificate)**: Certificate expired, wrong CN/SAN, untrusted CA.
- **Handshake failure (Alert 40)**: No mutually supported cipher suite or TLS version.
- **Decode error (Alert 50)**: Malformed message, often caused by middlebox (proxy, firewall) interfering.

---

## Identifying Retransmissions

### What Retransmissions Indicate
- **Sporadic retransmissions** (< 1%): Normal on any network. No action needed.
- **Sustained retransmissions** (1–5%): Congestion or intermittent packet loss. Investigate path quality.
- **High retransmissions** (> 5%): Significant packet loss. Likely network issue — MTU black hole, overloaded interface, or faulty NIC.

### Wireshark Analysis
```
# Show retransmission statistics
Statistics → TCP Stream Graphs → Throughput
Statistics → I/O Graphs (filter: tcp.analysis.retransmission)

# tshark command-line retransmission count
tshark -r capture.pcap -Y "tcp.analysis.retransmission" | wc -l
```

**Analysis only — verify against vendor documentation before applying.**
