// Extension: cloud-networking (standalone)
// Self-contained cloud networking agent that bundles all 19 specialist
// roles and skills. No external extension dependencies required.
//
// Specialists: vnet-architect, firewall-engineer, load-balancer,
// dns-specialist, private-link, hybrid-connectivity, network-security,
// network-troubleshooter, vwan-sdwan, network-monitor, multi-cloud-net,
// pricing-analyst, iac-generator, container-networking, cdn-edge,
// network-automation, sase-sse, capacity-planner, ipv6-migration

import { joinSession } from "@github/copilot-sdk/extension";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SPECIALISTS = join(HERE, "specialists");

// ── Update check ───────────────────────────────────────────────────────
// Lightweight, async, throttled check against the GitHub repo for a newer
// version. Runs at most once every 24h, fully non-blocking, fails silently.
// Opt out via env var CLOUD_NETWORKING_NO_UPDATE_CHECK=1.

const UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24h
const UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/dmauser/cloud-networking/master/package.json";
const INSTALL_META_PATH = join(HERE, ".install-meta.json");
const UPDATE_STATE_PATH = join(HERE, ".update-check.json");

function semverGt(a, b) {
    const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
    const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
    for (let i = 0; i < 3; i++) {
        if ((pa[i] || 0) > (pb[i] || 0)) return true;
        if ((pa[i] || 0) < (pb[i] || 0)) return false;
    }
    return false;
}

async function readJsonSafe(path) {
    try { return JSON.parse(await readFile(path, "utf8")); } catch { return null; }
}

async function checkForUpdate(session) {
    if (process.env.CLOUD_NETWORKING_NO_UPDATE_CHECK === "1") return;

    try {
        const meta = await readJsonSafe(INSTALL_META_PATH);
        const installed = meta?.version;
        if (!installed) return; // no recorded version; nothing to compare against

        const state = (await readJsonSafe(UPDATE_STATE_PATH)) || {};
        if (state.lastCheck && Date.now() - state.lastCheck < UPDATE_CHECK_INTERVAL_MS) return;

        const ac = new AbortController();
        const timer = setTimeout(() => ac.abort(), 4000);
        const res = await fetch(UPDATE_MANIFEST_URL, { signal: ac.signal, headers: { "user-agent": "cloud-networking-extension" } });
        clearTimeout(timer);
        if (!res.ok) return;
        const remote = await res.json();
        const latest = remote?.version;
        if (!latest) return;

        const newState = { lastCheck: Date.now(), latest, installed };
        await writeFile(UPDATE_STATE_PATH, JSON.stringify(newState, null, 2) + "\n").catch(() => {});

        if (semverGt(latest, installed)) {
            const installType = meta.installType || "user";
            const cmd = installType === "project"
                ? "npx github:dmauser/cloud-networking update"
                : "npx github:dmauser/cloud-networking update";
            await session.log(
                `cloud-networking: update available — installed ${installed}, latest ${latest}. ` +
                `Run \`${cmd}\` to upgrade. See CHANGELOG.md for details. ` +
                `(Disable this check with CLOUD_NETWORKING_NO_UPDATE_CHECK=1.)`
            );
        }
    } catch {
        // never crash the extension because of an update check
    }
}

// ── File loaders ───────────────────────────────────────────────────────

// Specialist role/skill files are immutable for the lifetime of a session, so
// cache successful reads to avoid re-reading the same .md from disk on repeat
// cn_role/cn_skill calls. Failures are not cached.
const fileCache = new Map();

async function loadFile(path) {
    const cached = fileCache.get(path);
    if (cached !== undefined) return cached;
    try {
        const content = await readFile(path, "utf8");
        fileCache.set(path, content);
        return content;
    } catch (err) {
        return { textResultForLlm: `Failed to load: ${err.message}`, resultType: "failure" };
    }
}

// ── Specialist registry (single source of truth) ──────────────────────
// Every specialist's directory, domain, routing trigger, extra orchestration
// guidance, and skill catalog lives here. Routing, capabilities, the
// orchestration prompt, and skill loading are all generated from this object.

const REGISTRY = {
    vnet: {
        dir: "vnet-architect",
        domain: "VNet/Subnet Architecture",
        icon: "🏗️",
        trigger: /\b(VNet|VPC|virtual\s+network|subnet|address\s+(space|plan)|CIDR|hub[-\s]?spoke|peering|network\s+(design|topology|diagram)|IP\s+plan)/i,
        guidance: "Cover Azure VNets, AWS VPCs, and GCP VPCs. Cite cloud provider documentation. Diagram policy: Mermaid (`network-diagram`) is the default — always include one for every design, preferring official cloud-provider icons (Iconify refs like `logos:microsoft-azure`, `logos:aws`, `logos:google-cloud`) and falling back to emojis when no icon is available. After delivering the Mermaid diagram, offer to also generate Excalidraw (`excalidraw-diagram`) or draw.io (`drawio-diagram`) versions on request — do not generate them by default.",
        skills: {
            "address-planner": "IP address space planning — CIDR allocation, subnet sizing, supernetting, overlap avoidance across environments.",
            "hub-spoke-design": "Hub-spoke topology design with peering, transit, and shared services.",
            "peering-advisor": "VNet/VPC peering configuration, transitive routing analysis, peering limits.",
            "subnet-calculator": "Subnet math — CIDR splits, available IPs, reserved addresses per cloud provider.",
            "network-diagram": "Generate Mermaid network topology diagrams from infrastructure descriptions. Always prefers official cloud-provider icons.",
            "excalidraw-diagram": "Generate Excalidraw (.excalidraw JSON) network topology diagrams. Prefers official Azure/AWS/GCP icon libraries from libraries.excalidraw.com.",
            "drawio-diagram": "Generate draw.io (.drawio XML) network topology diagrams. Prefers native cloud-provider stencils (mxgraph.azure2, mxgraph.aws4, mxgraph.gcp2).",
            "migration-planner": "Plan network migrations — on-prem to cloud, cloud-to-cloud address space.",
        },
    },
    fw: {
        dir: "firewall-engineer",
        domain: "Firewall Engineering",
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
        icon: "💰",
        trigger: /\b(pric(e|ing)|cost\s+(estimat|compar|analy|optim|break)|egress\s+cost|data\s+transfer\s+cost|TCO|total\s+cost|network\s+cost|billing|budget|monthly\s+cost|how\s+much\s+(does|will|is)|cheaper|expensive|save\s+money|cost\s+saving|right[-\s]?siz)/i,
        guidance: "Covers Azure, AWS, and GCP networking costs. Prices are indicative — always verify against current vendor pricing pages.",
        skills: {
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
};

const PREFIXES = Object.keys(REGISTRY);

// Canonical public identifier for a specialist, e.g. "vnet" -> "cn_vnet".
// REGISTRY stays keyed by the short prefix internally; the cn_ form is what
// users/the model pass as the `specialist` argument and what all output shows.
const pub = (prefix) => `cn_${prefix}`;

// ── Resolution & normalization helpers ─────────────────────────────────

// Accepts the canonical "cn_vnet" form, the bare alias "vnet", or the
// directory name "vnet-architect" (all case-insensitive). Returns the short
// REGISTRY key, or null.
function resolveSpecialist(raw) {
    if (!raw) return null;
    let key = String(raw).trim().toLowerCase();
    key = key.replace(/^cn[_-]/, ""); // strip canonical cn_ prefix if present
    if (REGISTRY[key]) return key;
    for (const [prefix, def] of Object.entries(REGISTRY)) {
        if (def.dir === key) return prefix;
    }
    return null;
}

// Accepts a skill in any of these forms and returns the canonical kebab name:
//   "address-planner", "address_planner", "vnet_skill_address_planner",
//   "skill_address_planner", "vnet-skill-address-planner", "cn_vnet_skill_address_planner"
function normalizeSkillName(prefix, raw) {
    let s = String(raw || "").trim().toLowerCase();
    s = s.replace(/^cn[_-]/, ""); // tolerate canonical "cn_<prefix>_skill_" form
    if (prefix) s = s.replace(new RegExp(`^${prefix}[_-]skill[_-]`), "");
    s = s.replace(/^[a-z0-9]+[_-]skill[_-]/, ""); // any "<prefix>_skill_" form
    s = s.replace(/^skill[_-]/, "");
    s = s.replace(/_/g, "-");
    return s;
}

// If a caller passes a legacy full name as the skill (e.g. "fw_skill_rule_audit"
// or "cn_fw_skill_rule_audit") without a specialist, infer the specialist from
// the leading prefix.
function inferSpecialistFromSkill(raw) {
    const m = String(raw || "").trim().toLowerCase()
        .replace(/^cn[_-]/, "")
        .match(/^([a-z0-9]+)[_-]skill[_-]/);
    if (m && REGISTRY[m[1]]) return m[1];
    return null;
}

// ── Output builders ────────────────────────────────────────────────────

function specialistList() {
    return PREFIXES.map((p, i) => `| ${i + 1} | ${REGISTRY[p].icon} | ${REGISTRY[p].domain} | \`${pub(p)}\` | ${Object.keys(REGISTRY[p].skills).length} |`).join("\n");
}

let _capabilitiesSummary = null;
function buildCapabilitiesSummary() {
    if (_capabilitiesSummary !== null) return _capabilitiesSummary;
    const rows = specialistList();
    const skillBlocks = PREFIXES.map((p) => {
        const def = REGISTRY[p];
        const skills = Object.entries(def.skills)
            .map(([name, desc]) => `  - \`${name}\` — ${desc}`)
            .join("\n");
        return `### ${def.icon} ${def.domain} — \`specialist: "${pub(p)}"\`\n${skills}`;
    }).join("\n\n");

    _capabilitiesSummary = `# Cloud Networking — Available Specialists

This extension exposes its 19 specialists through **five tools**. Specialists are
identified by their \`cn_\`-prefixed id (e.g. \`cn_vnet\`) and selected by *argument*,
not by tool name. Skills are passed as a separate \`skill\` argument.

| # | | Domain | specialist | # skills |
|---|---|--------|-----------|----------|
${rows}

## How to use
1. \`cn_route\` with { query } — find the right specialist for a request (recommended first step when unsure).
2. \`cn_role\` with { specialist } — load the specialist's role definition (e.g. \`{ specialist: "cn_vnet" }\`).
3. \`cn_orchestrate\` with { specialist } — get the step-by-step workflow and skill catalog.
4. \`cn_skill\` with { specialist, skill } — load a specific skill's deep guidance.

**Important:** Names like \`cn_vnet_skill_address_planner\` or \`cn_fw_role\` that appear in
documentation are *references only* — they are NOT callable tools. Always invoke
through \`cn_role\`, \`cn_orchestrate\`, and \`cn_skill\` with arguments. The bare forms
(\`vnet\`, \`fw\`, …) are still accepted as aliases for the \`specialist\` argument.

## Firewall Vendor Coverage
Azure Firewall, AWS Network Firewall, GCP Cloud Firewall/Cloud Armor, Palo Alto (PAN-OS/Panorama/VM-Series/Prisma), Fortinet FortiGate, Check Point (R81+/CloudGuard), Cisco ASA/FTD, Juniper SRX/vSRX, Zscaler (ZIA/ZPA), Sophos XG/XGS, OPNsense, pfSense, VyOS, iptables/nftables

## IaC Generator — Supported Tools
Bicep, Terraform (azurerm/aws/google), Ansible (azure.azcollection/amazon.aws/google.cloud), ARM Templates

## Specialists and their skills
${skillBlocks}`;
    return _capabilitiesSummary;
}

function buildOrchestrator(prefix) {
    const def = REGISTRY[prefix];
    const skillLines = Object.entries(def.skills)
        .map(([name, desc]) => `  - \`${name}\` — ${desc}`)
        .join("\n");
    return `You are now operating as the **${def.dir}** agent — ${def.icon} ${def.domain}.

Workflow:
1. Call \`cn_role\` with { specialist: "${pub(prefix)}" } to load the full role definition (do this first).
2. For each relevant skill, call \`cn_skill\` with { specialist: "${pub(prefix)}", skill: "<name>" }.

Available skills (pass the name as the \`skill\` argument):
${skillLines}

${def.guidance}

IMPORTANT: Names such as \`${pub(prefix)}_skill_<name>\` or \`${pub(prefix)}_role\` that may appear in
documentation are references only — they are NOT callable tools. Always invoke skills via
\`cn_skill\` and the role via \`cn_role\`. End every analysis with:
"Analysis only — verify against vendor documentation before applying."`;
}

function routeQuery(query) {
    const text = String(query || "");
    const matches = PREFIXES.filter((p) => REGISTRY[p].trigger.test(text));
    if (matches.length === 0) {
        return "No specialist matched. Call `cn_capabilities` for the full map.\nAvailable specialists: " +
            PREFIXES.map((p) => `${pub(p)} (${REGISTRY[p].domain})`).join(", ");
    }
    const lines = [`Matched ${matches.length} specialist(s). Recommended call sequence:\n`];
    for (const p of matches) {
        const def = REGISTRY[p];
        const firstSkill = Object.keys(def.skills)[0];
        lines.push(`### ${def.icon} ${def.domain}`);
        lines.push("```");
        lines.push(`cn_role({ specialist: "${pub(p)}" })`);
        lines.push(`cn_orchestrate({ specialist: "${pub(p)}" })`);
        lines.push(`cn_skill({ specialist: "${pub(p)}", skill: "${firstSkill}" })   # ...and other skills as needed`);
        lines.push("```");
        lines.push("");
    }
    lines.push("Do not call legacy tool names like `" + pub(matches[0]) + "_role` directly — they are not registered tools.");
    return lines.join("\n");
}

function unknownSpecialistMsg(raw) {
    return {
        textResultForLlm:
            `Unknown specialist "${raw}". Call \`cn_skill\`/\`cn_role\`/\`cn_orchestrate\` with one of these \`specialist\` values:\n` +
            PREFIXES.map((p) => `- ${pub(p)} — ${REGISTRY[p].domain}`).join("\n"),
        resultType: "failure",
    };
}

// ── Tools (parameterized — only 5 registered, well under the 128 limit) ──

const SPECIALIST_PARAM = {
    type: "string",
    enum: PREFIXES.map(pub),
    description:
        "The specialist to engage. One of: " +
        PREFIXES.map((p) => `${pub(p)} (${REGISTRY[p].domain})`).join("; ") +
        ". Bare forms (vnet, fw, …) are also accepted as aliases.",
};

const tools = [
    {
        name: "cn_capabilities",
        description: "Returns a structured map of all 19 cloud networking specialists and their skills, plus how to invoke them via cn_role/cn_orchestrate/cn_skill. Use to discover what networking capabilities are available.",
        parameters: { type: "object", properties: {} },
        skipPermission: true,
        handler: async () => buildCapabilitiesSummary(),
    },
    {
        name: "cn_route",
        description: "Given a cloud networking query, returns the recommended specialist(s) and the exact cn_role/cn_orchestrate/cn_skill calls to make. Use when unsure which specialist handles a request.",
        parameters: {
            type: "object",
            properties: { query: { type: "string", description: "The user's networking query or task description" } },
            required: ["query"],
        },
        skipPermission: true,
        handler: async (args) => routeQuery(args?.query),
    },
    {
        name: "cn_role",
        description: "Load a cloud networking specialist's role definition (persona, workflow, guardrails). Call this first when engaging a specialist. Select the specialist via the `specialist` argument — there are no per-specialist role tools.",
        parameters: {
            type: "object",
            properties: { specialist: SPECIALIST_PARAM },
            required: ["specialist"],
        },
        skipPermission: true,
        handler: async (args) => {
            const prefix = resolveSpecialist(args?.specialist);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            return loadFile(join(SPECIALISTS, REGISTRY[prefix].dir, "agents", `${REGISTRY[prefix].dir}.md`));
        },
    },
    {
        name: "cn_orchestrate",
        description: "Return the step-by-step orchestration workflow and skill catalog for a cloud networking specialist. Select the specialist via the `specialist` argument.",
        parameters: {
            type: "object",
            properties: { specialist: SPECIALIST_PARAM },
            required: ["specialist"],
        },
        skipPermission: true,
        handler: async (args) => {
            const prefix = resolveSpecialist(args?.specialist);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            return buildOrchestrator(prefix);
        },
    },
    {
        name: "cn_skill",
        description: "Load deep domain guidance for a specific specialist skill. Provide `specialist` (e.g. \"cn_vnet\") and `skill` (e.g. \"address-planner\"). Legacy names like \"cn_vnet_skill_address_planner\" are also accepted as the `skill` value. Call cn_capabilities or cn_orchestrate to see valid skills.",
        parameters: {
            type: "object",
            properties: {
                specialist: { ...SPECIALIST_PARAM, description: SPECIALIST_PARAM.description + " May be omitted if `skill` is a legacy full name like \"cn_vnet_skill_address_planner\"." },
                skill: { type: "string", description: "The skill name, e.g. \"address-planner\". Underscores and legacy \"<specialist>_skill_\" prefixes are tolerated." },
            },
            required: ["skill"],
        },
        skipPermission: true,
        handler: async (args) => {
            let prefix = resolveSpecialist(args?.specialist) || inferSpecialistFromSkill(args?.skill);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            const def = REGISTRY[prefix];
            const skill = normalizeSkillName(prefix, args?.skill);
            if (!def.skills[skill]) {
                return {
                    textResultForLlm:
                        `Unknown skill "${args?.skill}" for specialist "${pub(prefix)}" (${def.domain}).\n` +
                        `Call \`cn_skill\` with one of these \`skill\` values:\n` +
                        Object.keys(def.skills).map((s) => `- ${s}`).join("\n"),
                    resultType: "failure",
                };
            }
            return loadFile(join(SPECIALISTS, def.dir, "skills", skill, "SKILL.md"));
        },
    },
];

// ── Startup registry validation (logs issues, never crashes) ───────────
// Verifies every role/skill .md referenced by the REGISTRY exists on disk.
// This is filesystem I/O that is only useful while developing the extension —
// in a published install the layout is static and already covered by CI/tests.
// It is therefore opt-in (set CLOUD_NETWORKING_VALIDATE=1) and, when enabled,
// performs its reads concurrently rather than serially.

async function fileMissing(path) {
    try { await readFile(path, "utf8"); return false; } catch { return true; }
}

async function validateRegistry(session) {
    if (process.env.CLOUD_NETWORKING_VALIDATE !== "1") return [];

    const problems = [];
    const seen = new Set();
    const checks = [];
    for (const [prefix, def] of Object.entries(REGISTRY)) {
        if (seen.has(prefix)) problems.push(`duplicate prefix: ${prefix}`);
        seen.add(prefix);
        try { def.trigger.test(""); } catch { problems.push(`invalid trigger regex: ${prefix}`); }
        const roleMd = join(SPECIALISTS, def.dir, "agents", `${def.dir}.md`);
        checks.push(fileMissing(roleMd).then((m) => { if (m) problems.push(`missing role md: ${def.dir}`); }));
        for (const skill of Object.keys(def.skills)) {
            const md = join(SPECIALISTS, def.dir, "skills", skill, "SKILL.md");
            checks.push(fileMissing(md).then((m) => { if (m) problems.push(`missing skill md: ${prefix}/${skill}`); }));
        }
    }
    await Promise.all(checks);
    if (problems.length) {
        await session.log(`cloud-networking: registry validation found ${problems.length} issue(s): ${problems.join("; ")}`);
    }
    return problems;
}

// ── Register session ───────────────────────────────────────────────────

// Matches the extension name in any form: @cloud-networking, cloud-networking,
// cloud networking, cloudnetworking (with or without a leading @).
const MENTION_RE = /(^|[^\w])@?cloud[\s_-]?networking\b/i;

const TOOL_USAGE_NOTE =
    "You MUST use ONLY these cloud-networking tools: `cn_route`, `cn_role`, `cn_orchestrate`, `cn_skill`, `cn_capabilities`. " +
    "You MUST NOT read, open, list, or search the specialist files under `specialists/**` directly with any file/view/glob/grep/shell tool. " +
    "Always load specialist content via the registered `cn_role`, `cn_orchestrate`, and `cn_skill` tools — never by reading the `.md` files yourself. " +
    "Names like `cn_vnet_role` or `vnet_skill_address_planner` are NOT registered tools; select the specialist and skill via arguments, e.g. `cn_skill({ specialist: \"cn_vnet\", skill: \"address-planner\" })`. " +
    "Respond to the user in natural language — do not list or expose internal tool names.";

// ── Hook state ─────────────────────────────────────────────────────────
// Throttle the auto-routing hint: each specialist is announced at most once
// per session so repeated matching prompts don't crowd the context window.
const announcedPrefixes = new Set();
// Presence note is injected on session start AND (belt-and-suspenders) on the
// first user prompt, so the agent learns cloud-networking exists before it
// decides it doesn't know about it.
let presenceAnnounced = false;

const SPECIALIST_INLINE = PREFIXES.map((p) => `${REGISTRY[p].icon} ${REGISTRY[p].domain} (${pub(p)})`).join(", ");

// Canonical on-disk layout for any artifact a specialist produces (diagrams,
// reports, generated configs). Injected into the presence note so every
// specialist saves outputs to a predictable, easy-to-navigate structure.
const OUTPUT_CONVENTION =
    "OUTPUT FILES (REQUIRED LAYOUT): When you save ANY generated artifact to disk — diagrams, reports, or generated " +
    "configs/IaC — place it under a `cloud-networking/` folder in the current working directory, organized by specialist " +
    "then artifact type:\n" +
    "  cloud-networking/<specialist>/diagrams/  — Mermaid (.mmd), Excalidraw (.excalidraw), draw.io (.drawio)\n" +
    "  cloud-networking/<specialist>/reports/   — .md, .html, .pdf, .docx, .xlsx\n" +
    "  cloud-networking/<specialist>/configs/   — generated IaC, firewall/device configs, scripts\n" +
    "`<specialist>` is the specialist's kebab-case name (e.g. vnet-architect, firewall-engineer, iac-generator, pricing-analyst). " +
    "Name files `<kebab-topic>-<YYYYMMDD>.<ext>` (e.g. `hub-spoke-3region-20260528.drawio`). Create missing subfolders. " +
    "Confirm the path with the user before writing, write only inside the working directory, and never modify live infrastructure.";

const PRESENCE_NOTE =
    "[cloud-networking] The cloud-networking extension (a.k.a. @cloud-networking) is LOADED in this session. " +
    `It bundles ${PREFIXES.length} cloud-networking specialists: ${SPECIALIST_INLINE}. ` +
    "Discovery tools available right now: `cn_capabilities` (full specialist + skill map), `cn_route` (pick the right specialist for a query), " +
    "`cn_role` (load a specialist's role definition — call this FIRST before answering), `cn_orchestrate` (step-by-step workflow + skill catalog), " +
    "`cn_skill` (deep guidance for a specific skill). " +
    "When the user mentions VNets/VPCs, subnets/CIDR/IP planning, firewalls/NSGs/rule audits, load balancers, DNS, Private Link/private endpoints, " +
    "hybrid connectivity (VPN/ExpressRoute/Direct Connect/Interconnect), network security, connectivity troubleshooting/packet capture, " +
    "Virtual WAN/SD-WAN, network monitoring, multi-cloud networking, networking pricing/cost, IaC (Bicep/Terraform/Ansible) for networking, " +
    "container/Kubernetes networking, CDN/edge, network automation, SASE/SSE, capacity planning, or IPv6 migration — or says 'cloud-networking' / " +
    "'@cloud-networking' / 'this extension' / 'what can you do' in a networking context — you MUST call `cn_route` (or `cn_capabilities`) FIRST, " +
    "then the matched specialist's `cn_role`, before answering. " +
    "Do NOT answer networking questions from prior/general knowledge, and do NOT read the specialist files under `specialists/**` directly — " +
    "load ALL specialist content via `cn_role` / `cn_orchestrate` / `cn_skill`. " +
    "Never claim cloud-networking is unavailable: it is loaded. " +
    "Cloud Networking is analysis-only: it never applies changes, modifies infrastructure, or runs commands against live environments. " +
    "RESPONSE FOOTER (REQUIRED): at the end of EVERY assistant response that touches cloud networking — any turn where you called a `cn_*` tool, " +
    "or discussed any networking topic above — append the following line verbatim, on its own line after all other content:\n\n" +
    "> Analysis only — verify against vendor documentation before applying.\n\n" +
    OUTPUT_CONVENTION;

const DIRECT_MENTION =
    "[cloud-networking — DIRECT MENTION] The user just referenced the cloud-networking extension by name. " +
    `It IS loaded in this session (${tools.length} tools, ${PREFIXES.length} specialists). ` +
    "Do NOT tell the user cloud-networking is unavailable, unknown, or not part of the CLI. " +
    "REQUIRED next action: call the `cn_capabilities` tool now to retrieve the specialist map, then answer the user's question using that information. " +
    "If the user asked for examples or how to use it, after calling `cn_capabilities` summarize the specialists and suggest 3–5 concrete example prompts " +
    "(e.g. 'design a hub-spoke VNet topology across 3 regions', 'audit my Azure Firewall rules for shadowed or overly-broad entries', " +
    "'plan a non-overlapping IP address scheme for prod/dev/test', 'troubleshoot asymmetric routing through my NVA', " +
    "'compare NAT Gateway vs egress costs across Azure/AWS/GCP', 'generate Terraform for a dual-stack hub VPC'). " +
    "Remember the response-footer rule from the presence note: end this response with " +
    "'Analysis only — verify against vendor documentation before applying.'";

const session = await joinSession({
    tools,
    hooks: {
        onSessionStart: async () => {
            // Fires on startup / new / resume — inject the presence note as
            // session-level context so the agent knows cloud-networking exists
            // from turn 1 without waiting for a user prompt.
            presenceAnnounced = true;
            return { additionalContext: PRESENCE_NOTE };
        },
        onUserPromptSubmitted: async (input) => {
            if (!input?.prompt) return;

            const parts = [];

            // Fallback in case onSessionStart didn't fire (older CLI builds).
            if (!presenceAnnounced) {
                presenceAnnounced = true;
                parts.push(PRESENCE_NOTE);
            }

            // Strongest signal: the user literally named the extension. Always
            // inject the imperative (not throttled) so a follow-up prompt still
            // gets the nudge if the model previously ignored it.
            const mentioned = MENTION_RE.test(input.prompt);
            if (mentioned) parts.push(DIRECT_MENTION);

            const scanText = mentioned ? input.prompt.replace(MENTION_RE, " ") : input.prompt;
            const matches = PREFIXES.filter((p) => REGISTRY[p].trigger.test(scanText));
            const fresh = matches.filter((p) => !announcedPrefixes.has(p));

            if (fresh.length > 0) {
                for (const p of fresh) announcedPrefixes.add(p);
                const guidance = fresh
                    .map((p) => `• **${REGISTRY[p].icon} ${REGISTRY[p].domain}** — \`cn_role({ specialist: "${pub(p)}" })\` then \`cn_orchestrate({ specialist: "${pub(p)}" })\``)
                    .join("\n");
                parts.push(
                    `[cloud-networking] Detected networking intent. The following specialist(s) MUST handle this request:\n${guidance}\n\n` +
                    `Before producing ANY substantive networking answer, you MUST call the matched specialist's role via ` +
                    `\`cn_role({ specialist })\` FIRST. Do NOT answer from prior/general knowledge, and do NOT read the ` +
                    `specialist \`.md\` files under \`specialists/**\` directly. For each specialist call \`cn_role\` then ` +
                    `\`cn_orchestrate\` (with the shown \`specialist\` value), then the relevant \`cn_skill\` calls. ` +
                    `(This routing hint is shown once per specialist per session.)\n\n` +
                    TOOL_USAGE_NOTE,
                );
            } else if (mentioned && matches.length === 0) {
                parts.push(
                    `[cloud-networking] No single specialist matched directly. You MUST call \`cn_route\` with the user's ` +
                    `query (or \`cn_capabilities\`) to pick the right specialist BEFORE answering — do NOT answer ` +
                    `networking questions from prior/general knowledge.\n\n` +
                    TOOL_USAGE_NOTE,
                );
            }

            if (parts.length === 0) return;
            return { additionalContext: parts.join("\n\n") };
        },
    },
});

const totalSkills = PREFIXES.reduce((n, p) => n + Object.keys(REGISTRY[p].skills).length, 0);
await session.log(
    `cloud-networking loaded — ${PREFIXES.length} specialists, ${totalSkills} skills, ${tools.length} tools. Trigger with @cloud-networking`,
);

// Validate registry against the filesystem (non-blocking).
validateRegistry(session);

// Fire-and-forget update check (throttled to once per 24h, opt-out via env var).
checkForUpdate(session);
