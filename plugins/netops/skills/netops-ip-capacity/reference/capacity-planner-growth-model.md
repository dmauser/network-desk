# Capacity Growth Modeling — Skill Definition

## Purpose

Provide frameworks and methodologies for modeling network capacity growth driven by user expansion, application evolution, traffic pattern changes, and technology adoption. This skill enables long-term capacity planning with data-driven projections and budget justification.

## Core Knowledge

### Growth Driver Categories

#### 1. User/Device Growth
- End-user count expansion (employees, customers, partners)
- Device proliferation (BYOD, IoT, multi-device per user)
- Geographic expansion (new offices, regions, countries)
- M&A activity (sudden capacity jumps)

#### 2. Application Traffic Evolution
- New application deployments
- Migration from on-premises to cloud (traffic pattern shift)
- Microservices decomposition (traffic amplification)
- AI/ML workloads (large data movement)

#### 3. Infrastructure Changes
- Multi-cloud adoption (new interconnects needed)
- Zero-trust implementation (inspection overhead increases)
- Encryption everywhere (TLS inspection at scale)
- Observability expansion (telemetry data growth)

## User and Device Growth Projections

### Per-User Bandwidth Estimation

| User Type | Average Bandwidth | Peak Bandwidth | Daily Data |
|-----------|------------------|----------------|------------|
| Office worker (email, web, SaaS) | 2-5 Mbps | 10-20 Mbps | 2-5 GB |
| Developer (code, CI/CD, containers) | 5-15 Mbps | 30-50 Mbps | 5-15 GB |
| Video conference user | 3-8 Mbps per stream | 15-25 Mbps | 1-3 GB/hr |
| VDI/Remote Desktop user | 5-15 Mbps | 30-50 Mbps | 5-20 GB |
| Data analyst (dashboards, queries) | 5-20 Mbps | 50-100 Mbps | 10-50 GB |
| Media/Creative (video editing) | 20-100 Mbps | 200+ Mbps | 50-200 GB |
| IoT device (sensor/telemetry) | 10-100 Kbps | 1 Mbps | 10-500 MB |
| Security camera (HD) | 2-8 Mbps constant | 10 Mbps | 20-80 GB |
| Security camera (4K) | 12-25 Mbps constant | 30 Mbps | 100-250 GB |

### Device Proliferation Model
```
Devices per employee (typical enterprise):
- 2023 average: 3.2 devices/employee
- 2025 projection: 4.0 devices/employee (growth: 8% annually)
- Includes: laptop, phone, tablet, wearable, home IoT

Network impact:
- Not all devices active simultaneously
- Concurrency factor: 0.4-0.6 (40-60% active at any time)
- Per-device bandwidth varies significantly by type

Aggregate formula:
Required BW = users × devices_per_user × concurrency × avg_bw_per_device
```

### Geographic Expansion Model
```
New office/site bandwidth estimation:
1. Employee count × per-user bandwidth = local internet
2. Server/app traffic to cloud = site-to-cloud VPN/ER sizing
3. Inter-site collaboration = site-to-site bandwidth
4. Backup/replication = off-hours bulk transfer

Example - 200-person office:
- Internet: 200 × 10 Mbps peak = 2 Gbps (1 Gbps with 50% concurrency)
- Cloud connectivity: 200 × 5 Mbps = 1 Gbps (dedicated circuit)
- Inter-site: 20% of cloud traffic = 200 Mbps
- Backup: 500 GB nightly = ~47 Mbps sustained (8-hour window)
```

## Application Traffic Patterns

### East-West vs North-South

#### Definitions
- **North-South:** Traffic entering/leaving the network (internet, VPN, ExpressRoute)
- **East-West:** Traffic between workloads within the cloud (VNet-to-VNet, pod-to-pod)

#### Typical Ratios
| Architecture | East-West : North-South |
|--------------|------------------------|
| Traditional 3-tier | 20:80 |
| Modern cloud-native | 60:40 |
| Microservices | 80:20 |
| Data-intensive (Hadoop/Spark) | 90:10 |
| Hybrid (significant on-prem) | 40:60 |

#### Growth Implications
```
As architectures evolve from monolith → microservices:
- North-south may stay flat or grow slowly
- East-west grows exponentially
- Internal firewall/segmentation capacity must scale with east-west
- VNet peering and internal LB capacity become critical paths
```

### Microservices Traffic Amplification

#### Amplification Factor
```
Single user request → N internal service calls

Typical amplification factors:
- Simple CRUD API: 2-5× (auth + DB + cache)
- E-commerce checkout: 10-20× (cart, inventory, payment, shipping, notification)
- Social media feed: 20-50× (timeline, recommendations, ads, media, analytics)
- Search/discovery: 5-15× (query, rank, filter, personalize, log)

Network bandwidth amplification:
External request: 10 KB → Internal traffic: 10 KB × amplification × response sizes
Example: 10 KB × 15× × 2 (bidirectional) = 300 KB internal per external request
```

#### Service Mesh Overhead
```
Sidecar proxy (Envoy/Linkerd):
- Additional hop: +0.5-2 ms latency per hop
- Bandwidth overhead: 5-10% (headers, telemetry)
- Connection overhead: 2× connections (client→sidecar→service)
- mTLS: +3-5% CPU overhead per service

At scale (1000 services, 100K RPS):
- Sidecar connections: potentially millions
- Telemetry data: 5-15% of application traffic
- Plan for sidecar CPU/memory in capacity model
```

### Seasonal and Event-Driven Spikes

#### Common Seasonal Patterns
| Industry | Peak Period | Multiplier vs Baseline |
|----------|-----------|----------------------|
| Retail/E-commerce | Black Friday / Holiday | 3-10× |
| Education | September enrollment | 2-4× |
| Finance | Quarter-end / Tax season | 2-3× |
| Healthcare | Flu season / Enrollment | 1.5-3× |
| Media/Streaming | Premiere events | 5-20× |
| Gaming | Major releases / Events | 10-50× |
| Sports/Betting | Championship events | 5-20× |

#### Event-Driven Spike Planning
```
Formula:
Spike capacity = Baseline × spike_multiplier × confidence_factor

Where:
- spike_multiplier = historical peak / historical baseline (or estimate)
- confidence_factor = 1.2-1.5 (uncertainty buffer)

Capacity strategy:
- If spike < 2× baseline: Over-provision (always ready)
- If spike 2-5× baseline: Auto-scale + pre-warming
- If spike > 5× baseline: CDN/edge offload + burst cloud capacity + queue-based smoothing
```

#### Spike Duration and Recovery
```
Typical spike profiles:
- Flash sale: 15-60 minutes, sharp rise and fall
- Product launch: 2-4 hours, gradual ramp then plateau
- Holiday season: 4-6 weeks, gradual build and sustain
- DDoS/bot attack: Minutes to hours, unpredictable

Recovery time requirements:
- Auto-scale response: 5-15 minutes (Azure Firewall, App Gateway)
- Manual intervention: 30-60 minutes
- Pre-provisioned burst: Immediate (if already deployed)
```

## IoT and Telemetry Data Growth

### IoT Traffic Modeling
```
Per-device traffic formula:
Daily data = message_size × messages_per_day × (1 + overhead_factor)

Example - Industrial IoT sensor:
- Message size: 200 bytes
- Frequency: every 10 seconds = 8,640 messages/day
- Overhead (headers, ACKs): 40%
- Daily: 200 × 8,640 × 1.4 = 2.4 MB/day per sensor

At scale (10,000 sensors):
- Daily: 24 GB/day
- Peak (all reporting simultaneously): 10,000 × 200 × 1.4 / 10 = 280 KB/s = 2.2 Mbps
- Burst (firmware update): 10,000 × 50 MB = 500 GB (schedule off-peak)
```

### IoT Growth Projections
```
Industry averages:
- Connected IoT devices growing ~18% annually (2023-2028)
- Industrial IoT: 25-30% CAGR
- Consumer IoT: 15-20% CAGR
- Automotive/connected vehicles: 30%+ CAGR

Data per device growing ~25-40% annually:
- Higher resolution sensors
- More frequent reporting
- Video/audio added to previously data-only devices
- Edge AI requiring model updates

Combined growth (devices × data/device):
- Conservative: 40-50% annually
- Aggressive: 60-80% annually
```

## Video and Media Bandwidth

### Video Bandwidth Requirements
| Quality | Resolution | Bitrate (H.264) | Bitrate (H.265/HEVC) | Bitrate (AV1) |
|---------|-----------|-----------------|----------------------|---------------|
| SD | 480p | 1.5-3 Mbps | 0.75-1.5 Mbps | 0.5-1 Mbps |
| HD | 720p | 3-5 Mbps | 1.5-3 Mbps | 1-2 Mbps |
| Full HD | 1080p | 5-10 Mbps | 3-5 Mbps | 2-3.5 Mbps |
| 2K | 1440p | 10-16 Mbps | 5-8 Mbps | 3.5-6 Mbps |
| 4K UHD | 2160p | 20-40 Mbps | 10-20 Mbps | 7-14 Mbps |
| 8K | 4320p | 80-120 Mbps | 40-60 Mbps | 25-40 Mbps |

### Video Conferencing Growth Model
```
Per-user bandwidth (Microsoft Teams/Zoom):
- Audio only: 100 Kbps
- Video (720p): 1.5-2.5 Mbps
- Video (1080p): 3-5 Mbps
- Screen sharing: 1-2 Mbps
- Gallery view (25 tiles): 6-10 Mbps receive

Post-pandemic enterprise pattern:
- 40-60% of meetings include video
- Average 3-4 hours/day in meetings per knowledge worker
- Peak concurrent: 30-40% of workforce in meetings simultaneously

Capacity formula:
Video BW = employees × meeting_concurrency × avg_streams × bitrate_per_stream
Example: 5,000 × 0.35 × 2.5 streams × 3 Mbps = 13.1 Gbps peak
```

### Surveillance and Media Storage Growth
```
Camera growth: 10-15% annually (enterprise)
Resolution migration: HD → 4K over 3-5 year cycles
Storage implications: 4K = 4× bandwidth and storage of HD

Network capacity per camera:
- Continuous recording: bitrate × 24 × 3600 seconds/day
- Motion-triggered: bitrate × active_hours
- Smart compression (H.265+): 40-50% reduction vs H.264

Example campus (200 cameras migrating HD → 4K):
- Current (HD, H.264): 200 × 5 Mbps = 1 Gbps
- Year 2 (mix): 100 × 5 + 100 × 15 = 2 Gbps
- Year 4 (all 4K, H.265): 200 × 10 Mbps = 2 Gbps (codec savings)
- Year 4 (all 4K, H.264): 200 × 25 Mbps = 5 Gbps (without codec upgrade)
```

## Capacity Planning Spreadsheet Templates

### Growth Model Template (Formulas)
```
┌─────────────────────────────────────────────────────────────┐
│ CAPACITY GROWTH MODEL                                        │
├─────────────────────────────────────────────────────────────┤
│ INPUTS                                                       │
│ A1: Current baseline (Mbps)           = [measured P95]       │
│ A2: Monthly growth rate (%)           = [calculated CAGR/12] │
│ A3: Seasonal peak multiplier          = [historical max/avg] │
│ A4: Headroom factor                   = 1.3 (default)        │
│ A5: Planning horizon (months)         = 24                   │
│ A6: Current SKU capacity (Mbps)       = [from provider docs] │
│ A7: Next SKU capacity (Mbps)          = [from provider docs] │
│                                                              │
│ CALCULATIONS                                                 │
│ B1: Projected baseline (month N)      = A1 × (1+A2)^N       │
│ B2: Projected peak (month N)          = B1 × A3              │
│ B3: Required capacity (month N)       = B2 × A4              │
│ B4: Utilization current SKU (%)       = B3 / A6 × 100       │
│ B5: Months to 80% on current SKU      = solve B4 = 80       │
│ B6: Months to 80% on next SKU         = solve B3/A7 = 80    │
│                                                              │
│ DECISION                                                     │
│ C1: Upgrade needed by (month)         = B5                   │
│ C2: Lead time required (months)       = [procurement time]   │
│ C3: Decision deadline (month)         = C1 - C2              │
│ C4: Next SKU runway (months)          = B6                   │
│ C5: Cost delta (monthly)              = [next SKU - current] │
└─────────────────────────────────────────────────────────────┘
```

### Multi-Resource Capacity Tracker
```
┌───────────────────────────────────────────────────────────────────────┐
│ RESOURCE CAPACITY TRACKER                                              │
├──────────────────┬──────────┬──────────┬──────────┬──────────┬────────┤
│ Resource         │ Current  │ Limit    │ Usage %  │ Growth/mo│ Months │
│                  │ Usage    │          │          │          │ to 80% │
├──────────────────┼──────────┼──────────┼──────────┼──────────┼────────┤
│ VPN Tunnels      │ 22       │ 30       │ 73%      │ +2/mo    │ 1      │
│ VNet Peerings    │ 180      │ 500      │ 36%      │ +10/mo   │ 22     │
│ Routes (UDR)     │ 280      │ 400      │ 70%      │ +8/mo    │ 5      │
│ NSG Rules        │ 450      │ 1,000    │ 45%      │ +15/mo   │ 23     │
│ Public IPs       │ 85       │ 1,000    │ 8.5%     │ +3/mo    │ 205    │
│ GW Throughput    │ 800 Mbps │ 1,250    │ 64%      │ +40/mo   │ 5      │
│ ER Utilization   │ 5.2 Gbps │ 10 Gbps  │ 52%      │ +200/mo  │ 14     │
│ SNAT Ports       │ 45,000   │ 64,512   │ 70%      │ +2,000   │ 3      │
├──────────────────┴──────────┴──────────┴──────────┴──────────┴────────┤
│ CRITICAL: VPN Tunnels (1 month), SNAT Ports (3 months)                │
│ ACTION NEEDED: Upgrade VPN GW to VpnGw4, add NAT Gateway PIP         │
└───────────────────────────────────────────────────────────────────────┘

Formula for "Months to 80%":
= (Limit × 0.8 - Current Usage) / Growth per month
```

### Cost Projection Template
```
┌───────────────────────────────────────────────────────────────┐
│ UPGRADE COST PROJECTION                                        │
├───────────────────┬──────────┬──────────┬──────────┬──────────┤
│ Quarter           │ Q1       │ Q2       │ Q3       │ Q4       │
├───────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Current monthly   │ $5,200   │ $5,200   │ $5,200   │ $5,200   │
│ Projected monthly │ $5,200   │ $5,200   │ $8,400   │ $8,400   │
│ (after upgrade)   │          │          │          │          │
│ Delta             │ $0       │ $0       │ +$3,200  │ +$3,200  │
│ Quarterly total   │ $15,600  │ $15,600  │ $25,200  │ $25,200  │
├───────────────────┼──────────┴──────────┴──────────┴──────────┤
│ Annual total      │ $81,600 (vs $62,400 at current = +$19,200) │
│ Cost per Mbps     │ Drops from $4.16 to $1.68 (60% reduction)  │
│ Justification     │ Avoids $180K/yr revenue risk from outages   │
└───────────────────┴───────────────────────────────────────────┘
```

## Refresh Cycles and Upgrade Planning

### Technology Refresh Timelines
| Component | Typical Refresh | Trigger for Early Refresh |
|-----------|----------------|--------------------------|
| VPN Gateway SKU | 2-3 years | Hitting 80% capacity, new features needed |
| ExpressRoute circuit | 3-5 years | Hitting 70% sustained, new region |
| Firewall (managed) | Continuous (autoscale) | Performance degradation, new threats |
| Load Balancer | 3-5 years | Major version (v1→v2), feature gap |
| NVA/Virtual Appliance | 2-3 years | EOL, performance ceiling, vulnerability |
| WAN optimization | 3-4 years | Protocol evolution (QUIC), cloud-native migration |

### Planning Timeline Template
```
Month -12: Annual capacity review
  → Analyze growth trends from past 12 months
  → Project next 24-month requirements
  → Identify resources approaching 70% utilization

Month -9: Architecture assessment
  → Determine if current architecture can scale
  → Evaluate re-platform options if hitting limits
  → Develop 2-3 options with cost/benefit analysis

Month -6: Budget submission
  → Submit CapEx/OpEx request for next fiscal year
  → Include capacity data, growth projections, risk assessment
  → Present options to leadership with recommendations

Month -3: Procurement/provisioning
  → Initiate change request / purchase order
  → Order circuits (ExpressRoute/Direct Connect: 4-8 week lead time)
  → Schedule deployment window

Month 0: Implementation
  → Deploy new capacity
  → Validate performance
  → Update monitoring thresholds
  → Document new baselines

Month +1: Verification
  → Confirm capacity headroom restored
  → Validate no performance regressions
  → Update capacity model with new limits
```

## Budget Justification Framework

### Cost of Insufficient Capacity
```
Risk categories:
1. Packet loss → Retransmissions → Latency increase → User experience degradation
2. Connection failures → Transaction failures → Revenue loss
3. Gateway saturation → VPN disconnects → Productivity loss
4. Circuit exhaustion → Failover cascade → Outage

Quantification:
- Revenue per minute of downtime = annual_revenue / 525,600
- Productivity cost = affected_users × hourly_rate / 60
- SLA penalty = contract_penalties + credit_obligations
- Reputation cost = customer_churn × lifetime_value

Example justification:
"Upgrading from VpnGw2 ($548/mo) to VpnGw4 ($1,365/mo) costs $817/mo additional.
Current utilization at 85% with 40% annual growth means capacity exhaustion in 3 months.
One hour of VPN outage affects 2,000 remote workers at $75/hr = $150,000 lost productivity.
ROI: $817/mo investment prevents $150,000+ per incident risk."
```

### TCO Comparison Template
```
┌─────────────────────────────────────────────────────────────┐
│ TOTAL COST OF OWNERSHIP — UPGRADE OPTIONS                    │
├────────────────┬───────────────┬──────────────┬─────────────┤
│ Option         │ A: Do Nothing │ B: Scale-Up  │ C: Re-arch  │
├────────────────┼───────────────┼──────────────┼─────────────┤
│ Monthly cost   │ $5,200        │ $8,400       │ $12,000     │
│ Annual cost    │ $62,400       │ $100,800     │ $144,000    │
│ 3-year cost    │ $187,200      │ $302,400     │ $432,000    │
│ Capacity (Gbps)│ 1.25          │ 5.0          │ 20.0        │
│ Runway (months)│ 3             │ 18           │ 48+         │
│ Risk (outage)  │ HIGH          │ LOW          │ VERY LOW    │
│ Downtime cost  │ $450K (3 events)│ $0         │ $0          │
│ Net 3-yr cost  │ $637,200      │ $302,400     │ $432,000    │
│ Recommendation │               │ ★ BEST VALUE │             │
└────────────────┴───────────────┴──────────────┴─────────────┘
```

### Executive Summary Format
```
CAPACITY PLANNING RECOMMENDATION
─────────────────────────────────
SITUATION: [Resource] at [X%] utilization, growing [Y%] per month
IMPACT: Capacity exhaustion in [N] months → risk of [outcome]
REQUEST: Upgrade to [target SKU/architecture] at [cost delta]
BENEFIT: [N]-month runway, [X%] risk reduction, [$Y] avoided loss
TIMELINE: Decision needed by [date], implementation [duration]
```

---

**Analysis only — verify against vendor documentation before applying.**
