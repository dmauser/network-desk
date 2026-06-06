// Specialist registry — single source of truth (dependency-free).
//
// Every specialist's directory, domain, routing trigger, extra orchestration
// guidance, and skill catalog lives here. The runtime extension
// (extension.mjs) and the plugin generator (scripts/build-plugin.mjs) both
// import this object so routing, capabilities, the orchestration prompt, skill
// loading, and the generated Copilot CLI plugin all derive from one definition.
//
// This module intentionally imports nothing (no @github/copilot-sdk, no
// node:*) so it can be loaded by a plain Node process outside the CLI host.

export const REGISTRY = {
    vnet: {
        dir: "vnet-architect",
        domain: "VNet/Subnet Architecture",
        name: "VNet/Subnet Architect",
        summary: "CIDR/IP planning, hub-spoke, peering, subnet math, topology diagrams (ASCII console default; Mermaid/Excalidraw/draw.io on request)",
        icon: "🏗️",
        trigger: /\b(VNet|VPC|virtual\s+network|subnet|address\s+(space|plan)|CIDR|hub[-\s]?spoke|peering|network\s+(design|topology|diagram)|IP\s+plan)/i,
        guidance: "Cover Azure VNets, AWS VPCs, and GCP VPCs. Cite cloud provider documentation. Diagram policy: in the console, render topologies as a text/ASCII diagram (`ascii-diagram`) by default — zero rendering setup, works in any terminal. After delivering the ASCII diagram, offer to also generate richer formats on request: Mermaid (`network-diagram`), Excalidraw (`excalidraw-diagram`), or draw.io (`drawio-diagram`) — do not generate them by default. When you do produce Mermaid/draw.io/Excalidraw, prefer official cloud-provider icons (Iconify refs like `logos:microsoft-azure`, `logos:aws`, `logos:google-cloud` / native stencils) and fall back to emojis when no icon is available.",
        skills: {
            "address-planner": "IP address space planning — CIDR allocation, subnet sizing, supernetting, overlap avoidance across environments.",
            "hub-spoke-design": "Hub-spoke topology design with peering, transit, and shared services.",
            "peering-advisor": "VNet/VPC peering configuration, transitive routing analysis, peering limits.",
            "subnet-calculator": "Subnet math — CIDR splits, available IPs, reserved addresses per cloud provider.",
            "ascii-diagram": "Console-default text/ASCII topology diagrams using box-drawing characters. Zero rendering setup; works in any terminal. Use for every topology shown inline.",
            "network-diagram": "Generate Mermaid network topology diagrams from infrastructure descriptions. Opt-in richer format; always prefers official cloud-provider icons.",
            "excalidraw-diagram": "Generate Excalidraw (.excalidraw JSON) network topology diagrams. Prefers official Azure/AWS/GCP icon libraries from libraries.excalidraw.com.",
            "drawio-diagram": "Generate draw.io (.drawio XML) network topology diagrams. Prefers native cloud-provider stencils (mxgraph.azure2, mxgraph.aws4, mxgraph.gcp2).",
            "migration-planner": "Plan network migrations — on-prem to cloud, cloud-to-cloud address space.",
        },
    },
    fw: {
        dir: "firewall-engineer",
        domain: "Firewall Engineering",
        name: "Firewall Engineer",
        summary: "Rule audits, policy design/test, vendor migration, config gen, HA, log analysis (14 vendors)",
        icon: "🔥",
        trigger: /\b(firewall|FW\s+(rule|policy)|PAN[-\s]?OS|FortiGate|FortiOS|Check\s*Point|CloudGuard|ASA|FTD|Firepower|SRX|Zscaler|ZIA|ZPA|Sophos\s+XG|Azure\s+Firewall|AWS\s+Network\s+Firewall|Cloud\s+Armor|WAF\s+rule|rule\s+audit|firewall\s+policy|NGFW|network\s+virtual\s+appliance|NVA\s+firewall|OPNsense|pfSense|VyOS|iptables|nftables|netfilter)/i,
        guidance: "Covers 14 vendor platforms: Azure Firewall, AWS Network Firewall, GCP Cloud Firewall, Palo Alto, FortiGate, Check Point, Cisco ASA/FTD, Juniper SRX, Zscaler, Sophos XG, OPNsense, pfSense, VyOS, iptables/nftables. Analysis only — never apply changes without confirmation.",
        skills: {
            "rule-audit": "Audit firewall rules for shadow rules, overly permissive entries, unused rules, hit-count analysis. Multi-vendor.",
            "policy-design": "Design firewall policies from requirements — zone-based, app-aware, or L3/L4. Multi-vendor.",
            "policy-test": "Validate firewall rules before/after deploy — vendor simulators, log-driven shadow testing, automated rule-coverage test cases, pre-deployment checklist.",
            "vendor-migrate": "Migrate firewall rules between vendor platforms (e.g., PAN-OS → FortiGate, ASA → Azure Firewall).",
            "config-gen": "Generate vendor-specific firewall configuration from a policy intent description.",
            "hardening-check": "Security hardening checklist per vendor best practices.",
            "ha-design": "Firewall high-availability design per vendor — active/passive, active/active, clustering.",
            "log-analysis": "Parse and analyze firewall logs (syslog, CEF, LEEF) for security events.",
            "troubleshoot": "Troubleshoot firewall connectivity — packet flow, NAT, routing, policy lookup. Multi-vendor.",
        },
    },
    lb: {
        dir: "load-balancer",
        domain: "Load Balancing",
        name: "Load Balancer",
        summary: "L4/L7 selection, health probes, TLS offload/certs, WAF rules, routing, troubleshooting",
        icon: "⚖️",
        trigger: /\b(load\s+balanc|ALB|NLB|GLB|App(lication)?\s+Gateway|Front\s+Door|Traffic\s+Manager|health\s+probe|backend\s+pool|SNAT\s+exhaust|SSL\s+offload|L[47]\s+balanc|ingress\s+controller)/i,
        guidance: "Covers Azure LB/App Gateway/Front Door, AWS ALB/NLB/GLB, GCP LB.",
        skills: {
            "lb-selector": "Recommend the right LB type (L4 vs L7, regional vs global, internal vs public) based on requirements.",
            "health-probe-design": "Design health probe strategies — intervals, thresholds, custom probes, grace periods.",
            "ssl-offload": "TLS/SSL termination design — cert management, cipher suites, end-to-end encryption.",
            "tls-cert-mgmt": "TLS certificate lifecycle for load balancers — cert sources, storage (Key Vault/ACM/Secret Manager/cert-manager), per-LB deployment, SNI/ALPN, rotation, monitoring, emergency revocation.",
            "waf-rules": "WAF rule configuration — OWASP rulesets, custom rules, exclusions, tuning.",
            "traffic-routing": "Traffic routing methods — weighted, priority, geographic, latency-based, session affinity.",
            "troubleshoot": "Troubleshoot LB issues — backend health, asymmetric routing, SNAT exhaustion, 502/504 errors.",
        },
    },
    dns: {
        dir: "dns-specialist",
        domain: "DNS",
        name: "DNS Specialist",
        summary: "Zone/resolver design, DNSSEC, record audits, migrations, resolution debugging",
        icon: "🌐",
        trigger: /\b(DNS|domain\s+name|name\s+resolution|Route\s*53|Cloud\s+DNS|Private\s+DNS|DNS\s+(zone|resolver|forward|record|migration)|split[-\s]?horizon|conditional\s+forward)/i,
        guidance: "Covers Azure DNS, AWS Route 53, GCP Cloud DNS, and hybrid DNS resolution.",
        skills: {
            "zone-design": "DNS zone architecture — public vs private, split-horizon, zone delegation.",
            "resolver-design": "DNS resolver/forwarder topology — conditional forwarding, DNS Private Resolver, Route 53 Resolver.",
            "record-audit": "Audit DNS records for stale entries, misconfigurations, TTL issues.",
            "dnssec-design": "DNSSEC end-to-end design — algorithm selection, KSK/ZSK/CSK, signing automation, DS-record delegation, NSEC3, key rollover, monitoring. Azure DNS, Route 53, Cloud DNS, BIND.",
            "migration-plan": "Plan DNS migrations — zone transfers, cutover strategies, TTL lowering.",
            "troubleshoot": "Troubleshoot DNS resolution — nslookup/dig analysis, forwarding chain tracing.",
        },
    },
    pl: {
        dir: "private-link",
        domain: "Private Link / Endpoints",
        name: "Private Link Engineer",
        summary: "Endpoint design, private DNS integration, service exposure, security review",
        icon: "🔒",
        trigger: /\b(Private\s+(Link|Endpoint|Service\s+Connect)|PSC|service\s+endpoint|PE\s+(subnet|DNS)|PrivateLink)/i,
        guidance: "Covers Azure Private Link/Endpoints, AWS PrivateLink, GCP Private Service Connect.",
        skills: {
            "endpoint-design": "Private endpoint architecture — subnet placement, DNS integration, approval workflows.",
            "dns-integration": "Private DNS zone configuration for private endpoints — zone linking, A record management.",
            "service-exposure": "Expose services via Private Link Service / AWS PrivateLink / GCP PSC.",
            "security-review": "Review private endpoint security — NSG on PE subnets, network policies, access controls.",
            "troubleshoot": "Troubleshoot PE connectivity — DNS resolution, NSG blocks, approval state.",
        },
    },
    hyb: {
        dir: "hybrid-connectivity",
        domain: "Hybrid Connectivity",
        name: "Hybrid Connectivity",
        summary: "VPN, ExpressRoute/Direct Connect, BGP, bandwidth, failover/redundancy",
        icon: "🔗",
        trigger: /\b(ExpressRoute|Direct\s+Connect|Cloud\s+Interconnect|S2S\s+VPN|P2S\s+VPN|site[-\s]?to[-\s]?site|point[-\s]?to[-\s]?site|VPN\s+gateway|IPsec|IKEv[12]|BGP\s+(peer|neighbor|session)|hybrid\s+(connect|network))/i,
        guidance: "Covers ExpressRoute, VPN gateways, AWS Direct Connect, GCP Cloud Interconnect.",
        skills: {
            "vpn-design": "VPN gateway design — S2S, P2S, IKEv2/OpenVPN, BGP, active-active, custom IPsec policies.",
            "expressroute-design": "ExpressRoute / Direct Connect / Cloud Interconnect circuit design, peering, and routing.",
            "bgp-design": "Dedicated BGP design for cloud hybrid — ASN allocation, prefix/AS-PATH filters, attribute manipulation, multi-circuit active/active and active/passive, BFD, convergence tuning.",
            "bandwidth-calc": "Bandwidth planning — circuit sizing, aggregation, QoS, and cost estimation.",
            "routing-design": "BGP routing design — AS path manipulation, route filters, communities, local preference.",
            "failover-design": "Redundancy and failover — dual circuits, VPN backup, BFD, fast convergence.",
            "troubleshoot": "Troubleshoot hybrid connectivity — BGP neighbor state, tunnel status, MTU issues, asymmetric routing.",
        },
    },
    nsec: {
        dir: "network-security",
        domain: "Network Security",
        name: "Network Security",
        summary: "NSG/SG audits, segmentation, Zero Trust, WAF, DDoS, compliance (CIS/NIST/PCI)",
        icon: "🛡️",
        trigger: /\b(NSG|network\s+security\s+group|security\s+group|ASG|DDoS|micro[-\s]?segment|zero[-\s]?trust\s+network|flow\s+log\s+(analys|secur)|network\s+compliance|CIS\s+bench|network\s+segmentation)/i,
        guidance: "Covers NSGs, security groups, DDoS protection, micro-segmentation across all clouds.",
        skills: {
            "nsg-audit": "Audit NSG/Security Group rules — overly permissive, unused, conflicting, priority gaps.",
            "segmentation-design": "Network segmentation strategy — micro-segmentation, zero-trust network access.",
            "zero-trust-architecture": "Zero Trust networking architecture — NIST 800-207 / CISA ZTMM alignment, seven pillars, PEP/PDP placement, microsegmentation, east-west encryption, continuous verification, workload identity (SPIFFE).",
            "waf-policy-design": "Cross-cloud WAF policy design — five-layer model, Detect→Prevent rollout, OWASP CRS tuning, false-positive exclusions. Azure WAF, AWS WAFv2, GCP Cloud Armor, Cloudflare, F5, Imperva.",
            "ddos-design": "DDoS protection design — Azure DDoS Protection, AWS Shield, GCP Cloud Armor.",
            "flow-analysis": "Analyze NSG/VPC flow logs for security patterns, anomalies, top talkers.",
            "compliance-check": "Check network config against compliance frameworks (CIS, NIST, PCI-DSS network controls).",
            "troubleshoot": "Troubleshoot network security — blocked traffic, effective rules, IP flow verify.",
        },
    },
    ntsh: {
        dir: "network-troubleshooter",
        domain: "Network Troubleshooting",
        name: "Network Troubleshooter",
        summary: "Connectivity tests, packet capture, PCAP analysis, latency, routing, NAT, MTU, TLS",
        icon: "🔧",
        trigger: /\b(troubleshoot|packet\s+capture|traceroute|Network\s+Watcher|IP\s+flow\s+verify|connection\s+troubleshoot|latency\s+(issue|analys|spike)|routing\s+(table|debug|issue)|MTU|SNAT\s+port|NAT\s+(gateway|debug|issue)|Reachability\s+Analyzer)/i,
        guidance: "Uses Network Watcher, VPC Reachability Analyzer, and standard diagnostic tools. For packet-level investigations: pair `packet-capture` (capture mechanics) with `pcap-analysis` (deep analysis of the resulting .pcap/.pcapng).",
        skills: {
            "connectivity-test": "Connectivity testing strategy — TCP/ICMP probes, traceroute, Network Watcher tools.",
            "packet-capture": "Packet capture mechanics — how to capture (Azure Network Watcher, AWS VPC Traffic Mirroring, GCP Packet Mirroring, tcpdump), capture filters, where to tap, dual-point captures.",
            "pcap-analysis": "Deep PCAP analysis with Wireshark and tshark — Statistics & Expert Info workflows, TCP/TLS/DNS/HTTP playbooks, dual-point merging, decryption (TLS keylog, IPsec, WireGuard), anonymization, cloud-source gotchas.",
            "latency-analysis": "Latency troubleshooting — hop-by-hop analysis, RTT baselines, jitter measurement.",
            "routing-debug": "Routing table analysis — effective routes, UDR conflicts, BGP route propagation.",
            "nat-debug": "NAT troubleshooting — SNAT port exhaustion, DNAT rules, NAT gateway logs.",
            "mtu-path-discovery": "MTU/MSS troubleshooting — path MTU discovery, fragmentation, jumbo frames.",
            "tls-handshake-debug": "TLS handshake debugging — TLS alert code decoding, openssl s_client / testssl.sh / nmap workflows, cert chain validation, SNI/ALPN/mTLS failure patterns, OCSP stapling, middlebox interception detection.",
        },
    },
    vwan: {
        dir: "vwan-sdwan",
        domain: "Virtual WAN / SD-WAN",
        name: "Virtual WAN / SD-WAN",
        summary: "vWAN/secured-hub design, routing intent, NVA, branch connectivity",
        icon: "🌍",
        trigger: /\b(Virtual\s+WAN|vWAN|VWAN|routing\s+intent|secured\s+hub|SD[-\s]?WAN|inter[-\s]?hub|vWAN\s+hub)/i,
        guidance: "Covers Azure Virtual WAN hubs, routing intent, and SD-WAN partner integrations.",
        skills: {
            "vwan-design": "Virtual WAN topology design — hubs, connections, secured hubs, inter-hub routing.",
            "secured-vhub-design": "Azure Secured Virtual Hub design — when to use vs hub-spoke+NVA, routing intent, Azure Firewall vs partner NVA SKU selection, rule set design, forced-tunneling, HA & cross-region, observability, cost, common pitfalls.",
            "routing-intent": "Routing intent and routing policies — internet traffic, private traffic, inter-hub.",
            "nva-integration": "NVA integration in vWAN — BGP peering, managed appliances, SD-WAN partners.",
            "branch-connectivity": "Branch connectivity — S2S VPN, P2S, ExpressRoute to vWAN.",
            "troubleshoot": "Troubleshoot vWAN — effective routes, connection state, hub routing.",
        },
    },
    nmon: {
        dir: "network-monitor",
        domain: "Network Monitoring",
        name: "Network Monitor",
        summary: "Flow logs, traffic analytics, connection/synthetic monitors, alerts, dashboards",
        icon: "📊",
        trigger: /\b(network\s+monitor|Connection\s+Monitor|traffic\s+analytics|flow\s+log|network\s+(alert|dashboard|baseline|observ)|NSG\s+flow|VPC\s+flow|network\s+metric)/i,
        guidance: "Covers flow logs, traffic analytics, connection monitors, and alerting across all clouds.",
        skills: {
            "flow-log-setup": "Flow log configuration — NSG flow logs, VPC flow logs, storage/Log Analytics setup.",
            "traffic-analytics": "Traffic analytics setup and query — top talkers, geo distribution, malicious IPs.",
            "connection-monitor": "Connection monitor design — test groups, endpoints, alerting thresholds.",
            "synthetic-monitoring": "Proactive synthetic monitoring — Azure Connection Monitor, App Insights availability tests, AWS CloudWatch Synthetics, GCP Uptime Checks, Blackbox Exporter + Prometheus. Probe design, retries/multi-region thresholds, SLO/SLI integration.",
            "alert-design": "Network alerting strategy — metric alerts, log alerts, action groups, escalation.",
            "dashboard-build": "Network monitoring dashboard — KQL queries, Azure Monitor workbooks, CloudWatch.",
            "baseline-analysis": "Network baseline analysis — normal traffic patterns, anomaly detection.",
        },
    },
    mcn: {
        dir: "multi-cloud-net",
        domain: "Multi-Cloud Networking",
        name: "Multi-Cloud Networking",
        summary: "Transit design, cross-cloud addressing, service mapping, latency/cost comparison",
        icon: "☁️",
        trigger: /\b(multi[-\s]?cloud\s+(network|connect|transit)|cross[-\s]?cloud|cloud[-\s]?to[-\s]?cloud|transit\s+(architecture|design)|cloud\s+interconnect\s+design|service\s+mapping\s+(across|between)\s+cloud)/i,
        guidance: "Covers cross-cloud connectivity architectures, service equivalency mapping, and cost analysis.",
        skills: {
            "transit-design": "Multi-cloud transit architecture — VPN mesh, cloud-native interconnects, NVA transit.",
            "addressing-plan": "Cross-cloud IP address plan — non-overlapping CIDR, summarization, NAT strategies.",
            "service-mapping": "Map networking services across clouds (Azure VNet ↔ AWS VPC ↔ GCP VPC).",
            "latency-optimization": "Cross-cloud latency optimization — peering locations, backbone routing, CDN.",
            "cost-comparison": "Network cost comparison across clouds — egress, peering, VPN, interconnect pricing.",
        },
    },
    price: {
        dir: "pricing-analyst",
        domain: "Network Pricing",
        name: "Pricing Analyst",
        summary: "Egress/VPN/circuit/LB/firewall pricing, cross-cloud cost compare & optimization",
        icon: "💰",
        trigger: /\b(pric(e|ing)|retail\s+price|list\s+price|\$\/GB|per[-\s]?GB|hourly\s+rate|egress\s+price|cost\s+(estimat|compar|analy|optim|break)|egress\s+cost|data\s+transfer\s+cost|TCO|total\s+cost|network\s+cost|billing|budget|monthly\s+cost|how\s+much\s+(does|will|is)|cheaper|expensive|save\s+money|cost\s+saving|right[-\s]?siz)/i,
        guidance: "Covers Azure, AWS, and GCP networking costs. MANDATORY: every numeric price MUST be fetched from a live pricing API before it is quoted — never a hard-coded, cached, or model-recalled rate. Azure prices via the `retail-prices-api` skill (echo the $filter, region, SKU/meter, retailPrice, effectiveStartDate, currency, and retrieval timestamp); AWS prices via the AWS Price List Query API (GetProducts); GCP prices via the Cloud Billing Catalog API (services/.../skus) — each echoing the equivalent query, region/SKU, unit price, currency, and retrieval timestamp. Only fall back to values explicitly flagged 'INDICATIVE — not fetched from a live pricing API' when a provider's API is unreachable.",
        skills: {
            "retail-prices-api": "Fetch authoritative live Azure network rates from the Azure Retail Prices API — OData $filter for Bandwidth/egress, VPN/ExpressRoute gateways, Load Balancer/App Gateway, Azure Firewall, NAT Gateway, Public IP, Front Door, Private Link, DNS; region/SKU/meter selection, paging, currency. Also covers AWS (Price List Query API) and GCP (Cloud Billing Catalog API) for non-Azure rates.",
            "egress-calc": "Data transfer and egress cost calculation across Azure, AWS, and GCP — tiered pricing, inter-region, peering costs.",
            "egress-architecture": "Architectural patterns to structurally reduce egress cost — PrivateLink/Gateway Endpoints, CDN offload, regional pinning, dedicated interconnects, commit discounts. Break-even modeling.",
            "vpn-pricing": "VPN gateway pricing comparison — per-hour costs, tunnel limits, data transfer charges across all three clouds.",
            "circuit-pricing": "Dedicated circuit pricing — ExpressRoute, Direct Connect, Cloud Interconnect fees, break-even analysis vs VPN.",
            "lb-pricing": "Load balancer pricing — Azure LB/AppGW/Front Door, AWS ALB/NLB/GLB, GCP LB cost structures.",
            "firewall-pricing": "Firewall pricing — Azure Firewall tiers, AWS Network Firewall, GCP Cloud Armor, NVA marketplace costs.",
            "cost-optimizer": "Network cost optimization — reduce egress, right-size gateways, reserved capacity, architectural patterns to save.",
            "price-compare": "Cross-cloud network pricing comparison — side-by-side tables for equivalent services, workload scenario costs.",
        },
    },
    iac: {
        dir: "iac-generator",
        domain: "IaC Generator",
        name: "IaC Generator",
        summary: "Bicep, Terraform, Ansible, ARM for networking resources",
        icon: "📐",
        trigger: /\b(bicep|terraform|arm\s+template|ansible|infra(structure)?[-\s]+(as[-\s]+code|code)|IaC|generate\s+(bicep|terraform|arm|ansible)|network\s+deployment\s+(template|code)|deploy\s+network(ing)?\s+(template|code))/i,
        guidance: "Generates production-ready Infrastructure-as-Code for networking across Azure, AWS, and GCP. Supports Bicep, Terraform, Ansible, ARM. Code generation only — never executes deployments. Always provide validation commands before deployment commands.",
        skills: {
            "bicep-gen": "Generate Azure Bicep templates for networking resources — VNets, firewalls, VPN gateways, private endpoints, NSGs, route tables.",
            "terraform-gen": "Generate Terraform configurations for networking across Azure (azurerm), AWS (aws), and GCP (google) providers.",
            "ansible-gen": "Generate Ansible playbooks for network automation across Azure, AWS, and GCP using official collections.",
            "arm-gen": "Generate ARM JSON templates for Azure networking resources with parameter files and linked template patterns.",
        },
    },
    cnet: {
        dir: "container-networking",
        domain: "Container Networking",
        name: "Container Networking",
        summary: "CNI selection, network policy, service mesh, ingress, multi-cluster (AKS/EKS/GKE)",
        icon: "🐳",
        trigger: /\b(CNI|container\s+network|kubernetes\s+network|k8s\s+network|network\s+polic(y|ies)|service\s+mesh|istio|linkerd|cilium|calico|ingress\s+controller|Gateway\s+API|pod[-\s]+(to[-\s]+pod|network|cidr)|cluster\s+mesh|AKS\s+network|EKS\s+network|GKE\s+network)/i,
        guidance: "Covers Kubernetes/container networking across AKS, EKS, and GKE — CNI plugins, network policies, service mesh, ingress controllers, Gateway API, and multi-cluster connectivity.",
        skills: {
            "cni-selection": "CNI plugin comparison and selection — Azure CNI, Calico, Cilium, Flannel, WeaveNet. Decision matrix for AKS/EKS/GKE.",
            "network-policy": "Kubernetes network policies — native, Calico, Cilium. Namespace isolation, pod-level segmentation.",
            "service-mesh": "Service mesh design — Istio, Linkerd. mTLS, traffic splitting, observability, ambient vs sidecar.",
            "ingress-design": "Ingress and Gateway API — NGINX, Traefik, AGIC, ALB Controller. TLS termination, path/host routing.",
            "cross-cluster": "Multi-cluster networking — Submariner, ClusterMesh, Istio multi-cluster, Fleet Manager.",
            "troubleshoot": "Container networking troubleshooting — pod connectivity, CoreDNS, CNI failures, IP exhaustion, sidecar issues.",
        },
    },
    cdn: {
        dir: "cdn-edge",
        domain: "CDN & Edge Networking",
        name: "CDN & Edge Networking",
        summary: "Front Door/CloudFront/Cloud CDN, edge routing, caching, edge WAF",
        icon: "🌐",
        trigger: /\b(CDN|content\s+delivery|Front\s+Door|CloudFront|Cloud\s+CDN|edge\s+(network|routing|compute)|cache\s+(optim|strateg|key|purg)|origin\s+(shield|group|failover)|Anycast|POP\s+(location|select)|WAF\s+at\s+edge)/i,
        guidance: "Covers Azure Front Door, AWS CloudFront, GCP Cloud CDN, edge compute, caching strategies, and WAF at the edge.",
        skills: {
            "cdn-design": "CDN architecture — Azure Front Door, CloudFront, Cloud CDN. Origins, failover, private origins, HTTP/3.",
            "edge-routing": "Edge routing — Anycast, geo-routing, latency-based, edge compute (Rules Engine, Lambda@Edge, CloudFront Functions).",
            "cache-optimization": "Cache optimization — cache keys, TTL strategies, purge patterns, compression, streaming optimization.",
            "waf-edge": "Security at the edge — WAF policies, bot management, rate limiting, DDoS at CDN, geo-blocking.",
            "troubleshoot": "CDN troubleshooting — cache miss analysis, origin health, TLS issues, latency debugging, purge failures.",
        },
    },
    nauto: {
        dir: "network-automation",
        domain: "Network Automation & GitOps",
        name: "Network Automation & GitOps",
        summary: "CI/CD pipelines, drift detection, policy-as-code, testing, rollback",
        icon: "🔄",
        trigger: /\b(network\s+automat|GitOps\s+network|CI[\s/]?CD\s+network|pipeline\s+network|drift\s+detect|policy[-\s]+as[-\s]+code|network\s+testing|network\s+rollback|terraform\s+(pipeline|ci|automation)|bicep\s+(pipeline|ci|automation))/i,
        guidance: "Covers CI/CD pipelines for network changes, GitOps workflows, drift detection, policy-as-code, automated testing, and rollback strategies.",
        skills: {
            "pipeline-design": "CI/CD pipeline design for network IaC — GitHub Actions, Azure DevOps, stages, approvals, secrets.",
            "drift-detection": "Configuration drift detection — Terraform state drift, Resource Graph queries, AWS Config, remediation.",
            "policy-as-code": "Policy-as-code — Azure Policy, OPA/Rego, Checkov, tfsec. Enforce network governance pre-deployment.",
            "testing": "Network config testing — Terratest, Pester, pytest, smoke tests, integration tests, chaos engineering.",
            "rollback": "Rollback and change management — state rollback, blue-green, canary, blast radius control, validation gates.",
        },
    },
    sase: {
        dir: "sase-sse",
        domain: "SASE / SSE",
        name: "SASE / SSE",
        summary: "SASE architecture, ZTNA, SWG/CASB, SD-WAN integration, vendor comparison",
        icon: "🛡️",
        trigger: /\b(SASE|SSE|zero\s+trust\s+network|ZTNA|secure\s+web\s+gateway|SWG|CASB|cloud\s+access\s+security|FWaaS|Prisma\s+Access|Netskope|security\s+service\s+edge|private\s+access|internet\s+access\s+gateway)/i,
        guidance: "Covers SASE/SSE architecture, Zero Trust Network Access, SWG, CASB, SD-WAN integration, and vendor comparison (Zscaler, Palo Alto Prisma, Netskope, Microsoft, Cisco, Fortinet).",
        skills: {
            "architecture": "SASE/SSE architecture design — framework components, deployment models, migration from legacy VPN/proxy.",
            "ztna-design": "Zero Trust Network Access — identity-based access, app connectors, device posture, continuous trust.",
            "swg-casb": "Secure Web Gateway & CASB — URL filtering, TLS inspection, shadow IT, DLP, SaaS security posture.",
            "sdwan-integration": "SD-WAN with SASE integration — traffic steering, branch connectivity, QoS, vendor integrations.",
            "vendor-compare": "SASE/SSE vendor comparison — Zscaler, Palo Alto Prisma, Netskope, Cisco, Microsoft, Fortinet.",
        },
    },
    ncap: {
        dir: "capacity-planner",
        domain: "Network Capacity Planning",
        name: "Network Capacity Planning",
        summary: "Bandwidth forecasting, gateway sizing, throughput, scalability, growth",
        icon: "📏",
        trigger: /\b(capacity\s+plan|bandwidth\s+forecast|gateway\s+siz(e|ing)|throughput\s+calc|network\s+scalab|growth\s+model|network\s+limit|subscription\s+limit|scale\s+limit|network\s+capacity)/i,
        guidance: "Covers bandwidth forecasting, gateway/service sizing, throughput calculations, scalability limits, and growth modeling for cloud networking resources.",
        skills: {
            "bandwidth-forecast": "Bandwidth forecasting — traffic modeling, baseline establishment, growth projections, threshold alerts.",
            "gateway-sizing": "Gateway and service sizing — VPN GW SKUs, ExpressRoute, App Gateway capacity units, firewall throughput.",
            "throughput-calc": "Throughput calculations — TCP window/RTT, BDP, encryption overhead, multi-flow limits, SNAT ports.",
            "scalability-design": "Scalability patterns — subscription/account limits, horizontal scaling, when to split architectures.",
            "growth-model": "Growth modeling — user/device projections, traffic amplification, seasonal spikes, budget justification.",
        },
    },
    ipv6: {
        dir: "ipv6-migration",
        domain: "IPv6 Migration",
        name: "IPv6 Migration",
        summary: "Dual-stack design, transition planning, addressing, NAT64/DNS64, troubleshooting",
        icon: "🔢",
        trigger: /\b(IPv6|dual[-\s]?stack|NAT64|DNS64|464XLAT|IPv6\s+(migrat|transition|address|compat)|SLAAC|GUA|ULA|link[-\s]?local\s+address)/i,
        guidance: "Covers dual-stack design, IPv6 transition strategies, addressing schemes, NAT64/DNS64/464XLAT compatibility, and IPv6 troubleshooting across Azure, AWS, and GCP.",
        skills: {
            "dual-stack": "Dual-stack design — Azure/AWS/GCP dual-stack VNets/VPCs, LB support, DNS (A+AAAA), application considerations.",
            "transition-plan": "IPv6 transition strategies — phased migration, support matrix per cloud, rollback, success criteria.",
            "addressing": "IPv6 addressing schemes — GUA, ULA, /48 per site convention, subnet allocation, cloud-specific constraints.",
            "compatibility": "IPv4/IPv6 compatibility — NAT64, DNS64, 464XLAT, SIIT. When to use each mechanism.",
            "troubleshoot": "IPv6 troubleshooting — connectivity, ICMPv6, PMTUD, NDP, DNS resolution, firewall misconfigs.",
        },
    },
    doc: {
        dir: "report-builder",
        domain: "Documentation & Reporting",
        name: "Report Builder",
        summary: "Polished MD/HTML/PDF/DOCX reports & XLSX models from any specialist's findings",
        icon: "📄",
        trigger: /\b(create|generate|produce|prepare|build|export|render|package|compile)\b[^.\n]{0,60}\b(report|deliverable|documentation|write[-\s]?up|pdf|docx|word\s+document|xlsx|excel\s+(workbook|model)|html\s+report|workbook)\b|\b(report|deliverable|write[-\s]?up|analysis)\b[^.\n]{0,40}\b(as|to|into|in)\b[^.\n]{0,20}\b(pdf|docx|word|xlsx|excel|html|markdown)\b/i,
        guidance: "Packages findings from the domain specialists into polished deliverables (Markdown/HTML/PDF/DOCX/XLSX). This is a packaging/rendering specialist — do the technical analysis with the relevant domain specialist FIRST, then use report-builder to structure and render it. Renderer scripts ship in the extension's `renderers/` directory; render to the standard `network-desk/<specialist>/reports/` location and keep the Markdown/JSON source alongside the output. Rendering only — never modifies live infrastructure.",
        skills: {
            "report-structure": "Standard report skeleton (exec summary → scope → findings table → diagram → recommendations → references), quality checklist, and format-selection matrix.",
            "html-report": "Render a Markdown report to self-contained styled HTML via make_html.py (needs markdown2).",
            "pdf-report": "Render a Markdown report to print-ready PDF via make_pdf.py (Playwright + Chromium); falls back to HTML if Chromium is unavailable.",
            "docx-report": "Render a Markdown report to an editable Word doc with real styles + TOC via make_docx.py (needs python-docx).",
            "xlsx-workbook": "Build a multi-sheet Excel workbook with REAL formulas + named ranges from a JSON --spec via make_xlsx.py (needs openpyxl).",
        },
    },
};

// ── Per-cloud docs-MCP validation policy (shared, dependency-free) ───────────
//
// network-desk treats an official documentation MCP server as the primary source
// of truth for EACH cloud's facts:
//   • Azure → Microsoft Learn MCP (hosted HTTP, anonymous)
//   • AWS   → AWS Documentation MCP (local stdio via uvx; awslabs)
//   • GCP   → a configurable docs MCP (placeholder — swap when standardized)
// Firewall-vendor facts have no docs MCP and keep the "verify against vendor
// documentation" guardrail.
//
// MCP_PROVIDERS is the single source of truth for the wording below; both the
// runtime extension (extension.mjs) and the plugin generator
// (scripts/build-plugin.mjs) consume the derived MCP_VALIDATION_DIRECTIVE /
// MCP_VALIDATION_NOTE so every surface stays identical.

export const MCP_PROVIDERS = {
    azure: {
        cloud: "Azure",
        label: "Microsoft Learn MCP",
        serverName: "microsoft-learn",
        transport: "http",
        docDomain: "learn.microsoft.com",
        toolHints: "`microsoft_docs_search`, `microsoft_docs_fetch`, `microsoft_code_sample_search`",
        addCommand:
            "copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp",
        prereq: "",
    },
    aws: {
        cloud: "AWS",
        label: "AWS Documentation MCP",
        serverName: "aws-docs",
        transport: "stdio",
        docDomain: "docs.aws.amazon.com",
        toolHints: "`search_documentation`, `read_documentation`, `recommend`",
        addCommand:
            "copilot mcp add aws-docs --env FASTMCP_LOG_LEVEL=ERROR --env AWS_DOCUMENTATION_PARTITION=aws -- uvx awslabs.aws-documentation-mcp-server@latest",
        prereq: "requires `uv`/`uvx` + Python ≥3.10 (https://docs.astral.sh/uv/)",
    },
    gcp: {
        cloud: "GCP",
        label: "GCP Documentation MCP (configure)",
        serverName: "gcp-docs",
        transport: "stdio",
        docDomain: "cloud.google.com/docs",
        toolHints: "the configured GCP docs search/fetch tools",
        addCommand: "copilot mcp add gcp-docs -- <your-gcp-docs-mcp-command>",
        prereq: "placeholder — substitute your chosen GCP docs MCP server command",
    },
};

// Per-provider ⚠️ fallback banner (shown when that cloud's docs MCP is absent).
export function mcpFallbackBanner(key) {
    const p = MCP_PROVIDERS[key];
    const prereq = p.prereq ? ` (${p.prereq})` : "";
    return (
        `> ⚠️ **Unverified — ${p.label} server not configured.**\n` +
        `> This ${p.cloud} content is based on built-in/model knowledge and was NOT validated\n` +
        `> against ${p.docDomain}. Specs, limits, SKUs, and availability may be outdated. Configure\n` +
        `> the ${p.cloud} docs MCP server for authoritative validation${prereq}:\n` +
        "> `" + p.addCommand + "`"
    );
}

// Back-compat alias: the original Azure-only banner export.
export const MCP_FALLBACK_BANNER = mcpFallbackBanner("azure");

const _providerOrder = ["azure", "aws", "gcp"];

const _primaryLines = _providerOrder
    .map((k) => {
        const p = MCP_PROVIDERS[k];
        return (
            `   • ${p.cloud}: the ${p.label} server (tools like ${p.toolHints}). ` +
            `Cite the exact ${p.docDomain} URL(s) you validated against.`
        );
    })
    .join("\n");

const _fallbackBanners = _providerOrder.map((k) => mcpFallbackBanner(k)).join("\n>\n");

const _addCommands = _providerOrder
    .map((k) => {
        const p = MCP_PROVIDERS[k];
        const prereq = p.prereq ? `  — ${p.prereq}` : "";
        return `   • ${p.cloud}: \`${p.addCommand}\`${prereq}`;
    })
    .join("\n");

export const MCP_VALIDATION_DIRECTIVE =
    "VALIDATION POLICY (each cloud's official docs MCP is the primary source of truth):\n" +
    "1. PRIMARY — Before stating ANY cloud-networking fact (service SKUs/tiers, limits & quotas, " +
    "regional availability, feature support, pricing dimensions, and API/CLI/IaC syntax & versions), " +
    "you MUST validate it via THAT cloud's documentation MCP server:\n" +
    _primaryLines + "\n" +
    "   Treat the cloud's docs MCP as AUTHORITATIVE: if it contradicts internal specialist/skill " +
    "content or your own knowledge, THE DOCS MCP WINS — correct the answer and note the correction.\n" +
    "2. FALLBACK — Only if the relevant cloud's docs MCP is unavailable (tool absent, not configured, " +
    "or the call fails): answer from specialist/skill + model knowledge, but PREPEND the matching " +
    "banner below to your response and mark every numeric spec/limit \"indicative, unverified\". " +
    "Configure the missing server with the matching `copilot mcp add` command:\n" +
    _fallbackBanners + "\n" +
    "   Install commands:\n" +
    _addCommands + "\n" +
    "3. NEVER silently rely on model knowledge for a cloud fact — the user must always be able to tell " +
    "whether an answer was docs-MCP-validated (with URLs) or a fallback (with the ⚠️ banner).\n" +
    "4. SCOPE — Each docs MCP covers its own cloud only. For firewall-vendor facts there is no docs " +
    "MCP: validate against the official vendor documentation and keep the " +
    "\"Analysis only — verify against vendor documentation before applying.\" guardrail.";

// Compact one-liner for space-constrained surfaces (presence note, plugin scope blurbs).
export const MCP_VALIDATION_NOTE =
    "Validation-first: validate every cloud-networking fact against that cloud's official docs MCP " +
    "before stating it (the docs MCP wins on conflict; cite the doc URL) — Azure→Microsoft Learn " +
    "(`microsoft-learn`), AWS→AWS Documentation MCP (`aws-docs`), GCP→your configured `gcp-docs`. " +
    "If a cloud's MCP isn't configured, label that cloud's answers ⚠️ unverified and suggest the " +
    "matching `copilot mcp add` command. Firewall-vendor facts: verify against official vendor docs.";
