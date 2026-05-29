# Skill: PCAP Full Analysis (Wireshark / tshark / friends)

## Purpose

Deeply analyze packet capture files (`.pcap`, `.pcapng`, `.cap`) to root-cause network issues. This skill is the **analysis** companion to `ntsh_skill_packet_capture` (which covers *how to capture*). Use this skill when you already have a capture file in hand — from Azure Network Watcher, AWS VPC Traffic Mirroring, GCP Packet Mirroring, tcpdump, or a customer-supplied PCAP — and need to extract evidence.

**Workflow**:
1. Pair with `ntsh_skill_packet_capture` for capture mechanics (where, how, what to filter).
2. Use this skill to interpret the resulting PCAP and produce a written diagnosis with timestamps, filter expressions, and recommended fixes.

---

## Toolchain

| Tool | Role | Typical command |
|---|---|---|
| **Wireshark** (GUI) | Interactive exploration, Expert Info, Flow Graph, Statistics menus, decryption setup | `wireshark capture.pcapng` |
| **tshark** (CLI) | Scriptable, headless analysis — the analyst's workhorse for big captures and pipelines | `tshark -r capture.pcapng -Y "<filter>" -T fields -e <field>` |
| **capinfos** | Capture metadata: duration, packet count, encapsulation, hash, interface list | `capinfos -A capture.pcapng` |
| **editcap** | Slice, anonymize, change time, deduplicate, split by N seconds or N packets, fix bad checksums | `editcap -A "2024-01-01 12:00:00" -B "2024-01-01 12:05:00" in.pcapng slice.pcapng` |
| **mergecap** | Merge multiple captures in chronological order (essential for dual-point captures) | `mergecap -w merged.pcapng client.pcapng server.pcapng` |
| **reordercap** | Re-sort packets in strict time order (fixes capture corruption) | `reordercap in.pcapng out.pcapng` |
| **text2pcap** | Convert hex dumps / verbose logs to PCAP for inspection | `text2pcap -t '%Y-%m-%d %H:%M:%S.' hex.txt out.pcap` |
| **mergecap + editcap** | Combined slicing + merging for windowed diagnostics | |
| **Zeek** (formerly Bro) | Generate connection logs, DNS logs, HTTP logs, SSL logs from a PCAP (one row per flow) | `zeek -r capture.pcapng` → `conn.log`, `dns.log`, `ssl.log`, `http.log` |
| **tcpdump -r** | Quick read with classic BPF filters (when only tcpdump is available) | `tcpdump -r capture.pcap -nn 'tcp and port 443'` |
| **ngrep** | Grep-style payload search inside a PCAP | `ngrep -I capture.pcap "GET /api"` |
| **PcapPlusPlus / scapy / pyshark** | Programmatic / custom parsing | `pyshark.FileCapture('capture.pcapng', display_filter='http')` |
| **CloudShark / Packettotal / A-Packets** | Cloud-hosted analysis UIs for sharing | upload `.pcapng` |

Prefer **`.pcapng`** over `.pcap` — it preserves nanosecond timestamps, per-packet comments, multiple interfaces, and metadata that older `.pcap` drops.

---

## Step 1 — Profile the capture first

Always start with `capinfos` to ground the analysis:

```bash
capinfos -A -c -E -d -e -i -M -r -t -u capture.pcapng
```

Look at:
- **Duration** and **packet count** → sets the analysis scope.
- **First / last timestamp** → match against the user-reported incident window.
- **Number of interfaces** → multi-NIC captures need per-interface filters (`frame.interface_id == 0`).
- **Encapsulation** → Ethernet, Linux cooked, ERSPAN, VXLAN, GRE; affects which inner-protocol filters apply.
- **SHA-256** → quote in the report so anyone can verify they're analyzing the same file.

Then narrow with `editcap` if the file is huge:

```bash
# Slice to the incident window
editcap -A "2024-09-12 14:30:00" -B "2024-09-12 14:35:00" big.pcapng window.pcapng

# Split a 10 GB capture into 60-second chunks
editcap -i 60 big.pcapng split.pcapng
```

---

## Step 2 — tshark cheatsheet for common analyses

### TCP connection inventory

```bash
# Top conversations by bytes
tshark -r capture.pcapng -q -z conv,tcp

# All unique TCP 4-tuples with byte counts and durations
tshark -r capture.pcapng -q -z conv,tcp,ip.addr==10.1.0.0/16
```

### Retransmissions, out-of-order, duplicate ACKs

```bash
tshark -r capture.pcapng -Y "tcp.analysis.retransmission or tcp.analysis.fast_retransmission" \
       -T fields -e frame.time_relative -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport -e tcp.len

# Counts by host
tshark -r capture.pcapng -Y "tcp.analysis.retransmission" \
       -T fields -e ip.src | sort | uniq -c | sort -rn
```

### RTT and throughput

```bash
# Per-conversation RTT statistics (initial RTT, jitter, time-to-first-byte)
tshark -r capture.pcapng -q -z io,stat,1,"AVG(tcp.analysis.ack_rtt)tcp.analysis.ack_rtt"

# Throughput (bytes/sec, 1-second bins)
tshark -r capture.pcapng -q -z io,stat,1,"SUM(frame.len)frame.len"
```

### Window-scaling / zero-window stalls

```bash
tshark -r capture.pcapng -Y "tcp.analysis.zero_window or tcp.analysis.window_full" \
       -T fields -e frame.time_relative -e ip.src -e ip.dst -e tcp.window_size_value
```

### DNS latency and failures

```bash
# DNS response time per query
tshark -r capture.pcapng -Y "dns" -T fields \
       -e frame.time_relative -e dns.qry.name -e dns.flags.response -e dns.time -e dns.resp.addr -e dns.flags.rcode

# Failed queries (NXDOMAIN, SERVFAIL)
tshark -r capture.pcapng -Y "dns.flags.rcode != 0"
```

### TLS handshake inspection

```bash
# Client Hello → SNI, supported versions, ciphers
tshark -r capture.pcapng -Y "tls.handshake.type == 1" \
       -T fields -e frame.time_relative -e ip.src -e tls.handshake.extensions_server_name \
       -e tls.handshake.version -e tls.handshake.ciphersuite

# Server Hello → negotiated cipher and version
tshark -r capture.pcapng -Y "tls.handshake.type == 2" \
       -T fields -e ip.src -e tls.handshake.version -e tls.handshake.ciphersuite

# TLS alerts (fatal vs warning, alert code)
tshark -r capture.pcapng -Y "tls.alert_message" \
       -T fields -e frame.time_relative -e ip.src -e ip.dst -e tls.alert_message.level -e tls.alert_message.desc
```

### HTTP request/response timing

```bash
tshark -r capture.pcapng -Y "http.request or http.response" \
       -T fields -e frame.time_relative -e ip.src -e http.host -e http.request.method \
       -e http.request.uri -e http.response.code -e http.time
```

### Path MTU / fragmentation evidence

```bash
# Frag offsets > 0
tshark -r capture.pcapng -Y "ip.flags.mf == 1 or ip.frag_offset > 0"

# ICMP type 3 code 4 (frag needed but DF set) — PMTUD black hole signal
tshark -r capture.pcapng -Y "icmp.type == 3 and icmp.code == 4" \
       -T fields -e frame.time_relative -e ip.src -e ip.dst -e icmp.mtu
```

### Microbursts (sub-second utilization spikes)

```bash
tshark -r capture.pcapng -q -z io,stat,0.001,"SUM(frame.len)frame.len" \
  | awk '$2 ~ /^[0-9]/ && $4+0 > 1500000 {print}'
```

---

## Step 3 — Use Wireshark Statistics & Expert Info

Open the PCAP in Wireshark and use these menus methodically:

- **Statistics → Capture File Properties** — same as `capinfos`, plus per-packet annotations.
- **Statistics → Conversations** (TCP / UDP / IP) — sort by bytes, packets, duration; right-click → *Apply as Filter* to drill in.
- **Statistics → Endpoints** — top talkers and listeners by interface.
- **Statistics → I/O Graph** — overlay multiple display filters as time-series (e.g. retransmissions vs throughput vs RTT) on a single graph; export PNG for the report.
- **Statistics → TCP Stream Graphs → Round Trip Time** — visualize RTT growth and identify queue-buildup.
- **Statistics → TCP Stream Graphs → Throughput / Time-Sequence (tcptrace)** — diagnose slow starts, app-level stalls, send-window exhaustion.
- **Statistics → Service Response Time** (DNS, HTTP, SMB, LDAP) — per-call latency distributions.
- **Statistics → Protocol Hierarchy** — confirm the capture actually contains the protocols you expect (rules out wrong filter or wrong tap point).
- **Analyze → Expert Information** — pre-classified anomalies: warnings (zero window, retransmission, dup ACK), notes (window update, keep-alive), errors (malformed). Sort by count to find the dominant issue class instantly.
- **Analyze → Follow → TCP / TLS / HTTP Stream** — view the full application conversation in a single dialog; reveals app-layer errors invisible at the packet level.
- **Edit → Preferences → Protocols → TCP** — enable *Relative sequence numbers*, *Calculate conversation timestamps*, *Track number of bytes in flight*. These add columns that make stalls and BDP issues obvious.

---

## Step 4 — Diagnostic playbooks

### Slow downloads / long TTFB

1. Filter `tcp.stream eq <N>` for the failing flow.
2. Statistics → TCP Stream Graph → **Time-Sequence (tcptrace)** — look for flat horizontal periods (sender stall) vs flat vertical periods (receive-window full).
3. Check `tcp.analysis.bytes_in_flight` vs the BDP (RTT × bandwidth). If in-flight ≪ BDP, send window or app-level send is the bottleneck.
4. Check for `tcp.analysis.zero_window` from the receiver → CPU-bound consumer.
5. Check `tcp.analysis.duplicate_ack` and `tcp.analysis.fast_retransmission` → packet loss in transit; correlate with the IP path.

### TLS handshake failure

1. Filter `tls.handshake.type == 1 or tls.handshake.type == 2 or tls.alert_message`.
2. Verify Client Hello reaches the server (single-point capture may show only one side — capture both ends, then `mergecap`).
3. Inspect SNI vs the requested host (PrivateLink / proxy may rewrite); inspect ALPN.
4. Decode the alert: see `tls.alert_message.desc` — `handshake_failure (40)` = cipher mismatch, `unknown_ca (48)` = trust failure, `bad_certificate (42)` = expired/invalid cert, `internal_error (80)` = upstream error.
5. Hand off the cipher list and TLS version evidence to `lb_skill_ssl_offload` or `fw_skill_policy_design` for remediation.

### Intermittent latency / jitter

1. tshark IO graph at 100 ms bins for the duration; look for periodic spikes.
2. Compare RTT histograms across paths using `tcp.analysis.ack_rtt`.
3. If RTT spikes correlate with throughput floors → queue-buildup (bufferbloat) at a hop; capture at multiple points to localize.

### Asymmetric routing

1. Filter for SYN / SYN+ACK across both interfaces of a dual-point capture.
2. If SYN-ACK path differs from SYN path (different next-hop MAC or VLAN), you have asymmetry.
3. Hand off to `ntsh_skill_routing_debug`.

### MTU / fragmentation issues

1. Look for ICMP type 3 code 4 ("fragmentation needed and DF set") — see Step 2.
2. Look for repeated retransmissions of packets ≥ 1500 bytes that never get ACKed → PMTU black hole.
3. Hand off to `ntsh_skill_mtu_path_discovery`.

### NAT / source-port exhaustion

1. Filter SYNs from the suspected source; group by source port; check for rapid port reuse.
2. Check for `RST` immediately after SYN-ACK from the same 5-tuple — likely SNAT collision.
3. Hand off to `ntsh_skill_nat_debug` and `ncap_skill_gateway_sizing`.

### Dual-point capture analysis

When you have client-side and server-side PCAPs of the same flow:

```bash
# Sync clocks if needed
editcap -t -0.250 server.pcapng server-adjusted.pcapng

# Merge in time order
mergecap -w merged.pcapng client.pcapng server-adjusted.pcapng
```

Open `merged.pcapng`, filter `tcp.stream eq <N>`, and you'll see each packet appear twice — once on each interface. The time delta between the two appearances is the **one-way network latency** for that direction. Compare against expected RTT/2.

---

## Step 5 — Decryption when needed

### TLS

- Pre-master keys via SSLKEYLOGFILE: have the client (browser, curl, openssl) log keys to a file, then in Wireshark set *Edit → Preferences → Protocols → TLS → (Pre)-Master-Secret log filename*.
- For curl: `SSLKEYLOGFILE=/tmp/keys.log curl https://...`.
- For Firefox/Chrome: launch with `SSLKEYLOGFILE` env var set.
- RSA private key decryption works only for non-PFS cipher suites (rare now — most TLS uses ECDHE).

### IPsec / WireGuard / SMB / Kerberos

- IPsec: *Edit → Preferences → Protocols → ESP* — paste IKE SAs or ESP SPIs and keys.
- WireGuard: enable dissector and supply keys via the WireGuard preference panel.
- SMB3: provide session keys via *NTLMSSP* / *Kerberos* preferences.

---

## Step 6 — Anonymize before sharing

Before sending a PCAP outside your trust boundary:

```bash
# Strip payloads (keep headers only — typically enough for triage)
editcap -L -s 96 raw.pcapng safe.pcapng     # snaplen 96B keeps L2-L4 headers

# Anonymize IPs and MACs deterministically
tracewrangler --in raw.pcapng --out safe.pcapng --anonymize-ips --anonymize-macs
# (or pktanon / pcap_remote_filter / TraceAnon)

# Remove DNS query names, HTTP hosts, TLS SNI if sensitive
tshark -r raw.pcapng -Y "not dns and not tls.handshake.extensions_server_name and not http.host" \
       -w safe.pcapng
```

Always recompute `capinfos` on the anonymized file and re-share the new SHA-256.

---

## Step 7 — Cloud-specific PCAP sources & gotchas

| Source | Format | Gotchas |
|---|---|---|
| Azure Network Watcher (VM extension) | `.cap` (libpcap) | Captured at the NIC inside the guest — does NOT see traffic dropped before it hits the NIC. Cross-check with VNet flow logs by default; use NSG flow logs only where legacy deployments already exist (new creation blocked after 2025-06-30; retire 2027-09-30). |
| Azure vTAP (preview) / packet broker NVA | `.pcapng` | True wire capture; preserves VXLAN. |
| AWS VPC Traffic Mirroring | VXLAN-encapsulated; decode with VXLAN dissector or strip with editcap | Inner Ethernet preserved; ENI source is the mirror session; flow filters are SHA-based and lossy at high rates. |
| GCP Packet Mirroring | Raw mirror to a target ILB; capture on the collector VM | Captured packets retain original IPs but lose original ingress interface ID. |
| Container runtimes (containerd, CRI-O) | tcpdump inside a `nsenter` to the pod's netns | Veth pair shows pod-side only; need a host-side capture too for full path. |
| Service mesh sidecars (Envoy, Linkerd) | tcpdump on the sidecar's loopback for clear-text app traffic; encrypted on the wire | When TLS terminates in the sidecar, capture on loopback to see the app-layer payload. |
| ExpressRoute / Direct Connect | Capture on the edge router (provider-specific) or on the customer-edge router | Often only available via the carrier; consider mirror-port on the CE. |

---

## Step 8 — Verification checklist

Before delivering the diagnosis:

- [ ] `capinfos` quoted (duration, packet count, SHA-256, interfaces).
- [ ] The incident time window aligns with the capture window (with timezone explicit).
- [ ] At least one **dual-point capture** when the issue spans two hops, OR an explicit note that only one side is available and what that limits.
- [ ] The dominant Expert Info category is named and quantified.
- [ ] At least one **screenshot or exported PNG** of the IO Graph or TCP Stream Graph included in the report.
- [ ] Every claim ("server returned RST", "client retransmitted 12×") backed by a tshark filter the reader can re-run.
- [ ] Filter expressions are **copy-pasteable** and tested against the actual file.
- [ ] PCAP shared externally is **anonymized** and has a new SHA-256.
- [ ] Recommended fixes link to the specialist that owns the remediation (`fw_*`, `lb_*`, `dns_*`, `vnet_*`).

---

## References

- Wireshark User's Guide: https://www.wireshark.org/docs/wsug_html_chunked/
- tshark man page: https://www.wireshark.org/docs/man-pages/tshark.html
- Display Filter Reference: https://www.wireshark.org/docs/dfref/
- TCP analysis flags: https://www.wireshark.org/docs/wsug_html_chunked/ChAdvTCPAnalysis.html
- Sample captures: https://wiki.wireshark.org/SampleCaptures
- Zeek docs: https://docs.zeek.org/
- Azure Network Watcher packet capture: https://learn.microsoft.com/azure/network-watcher/network-watcher-packet-capture-overview
- AWS VPC Traffic Mirroring: https://docs.aws.amazon.com/vpc/latest/mirroring/
- GCP Packet Mirroring: https://cloud.google.com/vpc/docs/packet-mirroring

**Analysis only — verify against vendor documentation before applying.**
