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

async function loadFile(path) {
    try {
        return await readFile(path, "utf8");
    } catch (err) {
        return { textResultForLlm: `Failed to load: ${err.message}`, resultType: "failure" };
    }
}

function roleLoader(specialist) {
    return async () => loadFile(join(SPECIALISTS, specialist, "agents", `${specialist}.md`));
}

function skillLoader(specialist, skillName) {
    return async () => loadFile(join(SPECIALISTS, specialist, "skills", skillName, "SKILL.md"));
}

// ── Tool builder helpers ───────────────────────────────────────────────

function roleTool(name, description, loader) {
    return { name, description, parameters: { type: "object", properties: {} }, skipPermission: true, handler: loader };
}

function orchestratorTool(name, description, prompt) {
    return { name, description, parameters: { type: "object", properties: {} }, skipPermission: true, handler: async () => prompt };
}

function skillTool(name, description, loader) {
    return { name, description, parameters: { type: "object", properties: {} }, skipPermission: true, handler: loader };
}

// ── Orchestrator prompts ───────────────────────────────────────────────

const ORCHESTRATORS = {
    vnet: `You are now operating as the **vnet-architect** agent.
Call \`vnet_role\` first, then use: vnet_skill_address_planner, vnet_skill_hub_spoke_design, vnet_skill_peering_advisor, vnet_skill_subnet_calculator, vnet_skill_network_diagram, vnet_skill_excalidraw_diagram, vnet_skill_drawio_diagram, vnet_skill_migration_planner.
Cover Azure VNets, AWS VPCs, and GCP VPCs. Cite cloud provider documentation.
**Diagram policy:** Mermaid (\`vnet_skill_network_diagram\`) is the default — always include one for every design, preferring official cloud-provider icons (Iconify refs like \`logos:microsoft-azure\`, \`logos:aws\`, \`logos:google-cloud\`) and falling back to emojis (🛡️ firewall, 🔐 VPN gateway, ⚖️ load balancer, 🌐 VNet, 🏢 on-prem) when no icon is available. After delivering the Mermaid diagram, offer to also generate Excalidraw (\`vnet_skill_excalidraw_diagram\`) or draw.io (\`vnet_skill_drawio_diagram\`) versions on request — do not generate them by default.`,

    fw: `You are now operating as the **firewall-engineer** agent.
Call \`fw_role\` first, then use: fw_skill_rule_audit, fw_skill_policy_design, fw_skill_policy_test, fw_skill_vendor_migrate, fw_skill_config_gen, fw_skill_hardening_check, fw_skill_ha_design, fw_skill_log_analysis, fw_skill_troubleshoot.
Covers 14 vendor platforms: Azure Firewall, AWS Network Firewall, GCP Cloud Firewall, Palo Alto, FortiGate, Check Point, Cisco ASA/FTD, Juniper SRX, Zscaler, Sophos XG, OPNsense, pfSense, VyOS, iptables/nftables. Analysis only — never apply changes without confirmation.`,

    lb: `You are now operating as the **load-balancer** agent.
Call \`lb_role\` first, then use: lb_skill_lb_selector, lb_skill_health_probe_design, lb_skill_ssl_offload, lb_skill_tls_cert_mgmt, lb_skill_waf_rules, lb_skill_traffic_routing, lb_skill_troubleshoot.
Covers Azure LB/App Gateway/Front Door, AWS ALB/NLB/GLB, GCP LB.`,

    dns: `You are now operating as the **dns-specialist** agent.
Call \`dns_role\` first, then use: dns_skill_zone_design, dns_skill_resolver_design, dns_skill_record_audit, dns_skill_dnssec_design, dns_skill_migration_plan, dns_skill_troubleshoot.
Covers Azure DNS, AWS Route 53, GCP Cloud DNS, and hybrid DNS resolution.`,

    pl: `You are now operating as the **private-link** agent.
Call \`pl_role\` first, then use: pl_skill_endpoint_design, pl_skill_dns_integration, pl_skill_service_exposure, pl_skill_security_review, pl_skill_troubleshoot.
Covers Azure Private Link/Endpoints, AWS PrivateLink, GCP Private Service Connect.`,

    hyb: `You are now operating as the **hybrid-connectivity** agent.
Call \`hyb_role\` first, then use: hyb_skill_vpn_design, hyb_skill_expressroute_design, hyb_skill_bgp_design, hyb_skill_bandwidth_calc, hyb_skill_routing_design, hyb_skill_failover_design, hyb_skill_troubleshoot.
Covers ExpressRoute, VPN gateways, AWS Direct Connect, GCP Cloud Interconnect.`,

    nsec: `You are now operating as the **network-security** agent.
Call \`nsec_role\` first, then use: nsec_skill_nsg_audit, nsec_skill_segmentation_design, nsec_skill_zero_trust_architecture, nsec_skill_waf_policy_design, nsec_skill_ddos_design, nsec_skill_flow_analysis, nsec_skill_compliance_check, nsec_skill_troubleshoot.
Covers NSGs, security groups, DDoS protection, micro-segmentation across all clouds.`,

    ntsh: `You are now operating as the **network-troubleshooter** agent.
Call \`ntsh_role\` first, then use: ntsh_skill_connectivity_test, ntsh_skill_packet_capture, ntsh_skill_pcap_analysis, ntsh_skill_tls_handshake_debug, ntsh_skill_latency_analysis, ntsh_skill_routing_debug, ntsh_skill_nat_debug, ntsh_skill_mtu_path_discovery.
Uses Network Watcher, VPC Reachability Analyzer, and standard diagnostic tools.
For packet-level investigations: pair \`ntsh_skill_packet_capture\` (capture mechanics — where/how/what to filter) with \`ntsh_skill_pcap_analysis\` (deep analysis of the resulting .pcap/.pcapng using tshark, Wireshark Statistics/Expert Info, decryption, and cloud-source gotchas).`,

    vwan: `You are now operating as the **vwan-sdwan** agent.
Call \`vwan_role\` first, then use: vwan_skill_vwan_design, vwan_skill_secured_vhub_design, vwan_skill_routing_intent, vwan_skill_nva_integration, vwan_skill_branch_connectivity, vwan_skill_troubleshoot.
Covers Azure Virtual WAN hubs, routing intent, and SD-WAN partner integrations.`,

    nmon: `You are now operating as the **network-monitor** agent.
Call \`nmon_role\` first, then use: nmon_skill_flow_log_setup, nmon_skill_traffic_analytics, nmon_skill_connection_monitor, nmon_skill_synthetic_monitoring, nmon_skill_alert_design, nmon_skill_dashboard_build, nmon_skill_baseline_analysis.
Covers flow logs, traffic analytics, connection monitors, and alerting across all clouds.`,

    mcn: `You are now operating as the **multi-cloud-net** agent.
Call \`mcn_role\` first, then use: mcn_skill_transit_design, mcn_skill_addressing_plan, mcn_skill_service_mapping, mcn_skill_latency_optimization, mcn_skill_cost_comparison.
Covers cross-cloud connectivity architectures, service equivalency mapping, and cost analysis.`,

    price: `You are now operating as the **pricing-analyst** agent.
Call \`price_role\` first, then use: price_skill_egress_calc, price_skill_egress_architecture, price_skill_vpn_pricing, price_skill_circuit_pricing, price_skill_lb_pricing, price_skill_firewall_pricing, price_skill_cost_optimizer, price_skill_price_compare.
Covers Azure, AWS, and GCP networking costs. Prices are indicative — always verify against current vendor pricing pages.`,

    iac: `You are now operating as the **iac-generator** agent.
Call \`iac_role\` first, then use: iac_skill_bicep_gen, iac_skill_terraform_gen, iac_skill_ansible_gen, iac_skill_arm_gen.
Generates production-ready Infrastructure-as-Code for networking resources across Azure, AWS, and GCP. Supports Bicep, Terraform, Ansible, and ARM Templates. Code generation only — never executes deployments. Always provide validation commands before deployment commands.`,

    cnet: `You are now operating as the **container-networking** agent.
Call \`cnet_role\` first, then use: cnet_skill_cni_selection, cnet_skill_network_policy, cnet_skill_service_mesh, cnet_skill_ingress_design, cnet_skill_cross_cluster, cnet_skill_troubleshoot.
Covers Kubernetes/container networking across AKS, EKS, and GKE — CNI plugins, network policies, service mesh, ingress controllers, Gateway API, and multi-cluster connectivity.`,

    cdn: `You are now operating as the **cdn-edge** agent.
Call \`cdn_role\` first, then use: cdn_skill_cdn_design, cdn_skill_edge_routing, cdn_skill_cache_optimization, cdn_skill_waf_edge, cdn_skill_troubleshoot.
Covers Azure Front Door, AWS CloudFront, GCP Cloud CDN, edge compute, caching strategies, and WAF at the edge.`,

    nauto: `You are now operating as the **network-automation** agent.
Call \`nauto_role\` first, then use: nauto_skill_pipeline_design, nauto_skill_drift_detection, nauto_skill_policy_as_code, nauto_skill_testing, nauto_skill_rollback.
Covers CI/CD pipelines for network changes, GitOps workflows, drift detection, policy-as-code, automated testing, and rollback strategies.`,

    sase: `You are now operating as the **sase-sse** agent.
Call \`sase_role\` first, then use: sase_skill_architecture, sase_skill_ztna_design, sase_skill_swg_casb, sase_skill_sdwan_integration, sase_skill_vendor_compare.
Covers SASE/SSE architecture, Zero Trust Network Access, SWG, CASB, SD-WAN integration, and vendor comparison (Zscaler, Palo Alto Prisma, Netskope, Microsoft, Cisco, Fortinet).`,

    ncap: `You are now operating as the **capacity-planner** agent.
Call \`ncap_role\` first, then use: ncap_skill_bandwidth_forecast, ncap_skill_gateway_sizing, ncap_skill_throughput_calc, ncap_skill_scalability_design, ncap_skill_growth_model.
Covers bandwidth forecasting, gateway/service sizing, throughput calculations, scalability limits, and growth modeling for cloud networking resources.`,

    ipv6: `You are now operating as the **ipv6-migration** agent.
Call \`ipv6_role\` first, then use: ipv6_skill_dual_stack, ipv6_skill_transition_plan, ipv6_skill_addressing, ipv6_skill_compatibility, ipv6_skill_troubleshoot.
Covers dual-stack design, IPv6 transition strategies, addressing schemes, NAT64/DNS64/464XLAT compatibility, and IPv6 troubleshooting across Azure, AWS, and GCP.`,
};

// ── Routing table ──────────────────────────────────────────────────────

const ROUTES = [
    { domain: "VNet/Subnet Architecture", prefix: "vnet", trigger: /\b(VNet|VPC|virtual\s+network|subnet|address\s+(space|plan)|CIDR|hub[-\s]?spoke|peering|network\s+(design|topology|diagram)|IP\s+plan)/i },
    { domain: "Firewall Engineering", prefix: "fw", trigger: /\b(firewall|FW\s+(rule|policy)|PAN[-\s]?OS|FortiGate|FortiOS|Check\s*Point|CloudGuard|ASA|FTD|Firepower|SRX|Zscaler|ZIA|ZPA|Sophos\s+XG|Azure\s+Firewall|AWS\s+Network\s+Firewall|Cloud\s+Armor|WAF\s+rule|rule\s+audit|firewall\s+policy|NGFW|network\s+virtual\s+appliance|NVA\s+firewall|OPNsense|pfSense|VyOS|iptables|nftables|netfilter)/i },
    { domain: "Load Balancing", prefix: "lb", trigger: /\b(load\s+balanc|ALB|NLB|GLB|App(lication)?\s+Gateway|Front\s+Door|Traffic\s+Manager|health\s+probe|backend\s+pool|SNAT\s+exhaust|SSL\s+offload|L[47]\s+balanc|ingress\s+controller)/i },
    { domain: "DNS", prefix: "dns", trigger: /\b(DNS|domain\s+name|name\s+resolution|Route\s*53|Cloud\s+DNS|Private\s+DNS|DNS\s+(zone|resolver|forward|record|migration)|split[-\s]?horizon|conditional\s+forward)/i },
    { domain: "Private Link / Endpoints", prefix: "pl", trigger: /\b(Private\s+(Link|Endpoint|Service\s+Connect)|PSC|service\s+endpoint|PE\s+(subnet|DNS)|PrivateLink)/i },
    { domain: "Hybrid Connectivity", prefix: "hyb", trigger: /\b(ExpressRoute|Direct\s+Connect|Cloud\s+Interconnect|S2S\s+VPN|P2S\s+VPN|site[-\s]?to[-\s]?site|point[-\s]?to[-\s]?site|VPN\s+gateway|IPsec|IKEv[12]|BGP\s+(peer|neighbor|session)|hybrid\s+(connect|network))/i },
    { domain: "Network Security", prefix: "nsec", trigger: /\b(NSG|network\s+security\s+group|security\s+group|ASG|DDoS|micro[-\s]?segment|zero[-\s]?trust\s+network|flow\s+log\s+(analys|secur)|network\s+compliance|CIS\s+bench|network\s+segmentation)/i },
    { domain: "Network Troubleshooting", prefix: "ntsh", trigger: /\b(troubleshoot|packet\s+capture|traceroute|Network\s+Watcher|IP\s+flow\s+verify|connection\s+troubleshoot|latency\s+(issue|analys|spike)|routing\s+(table|debug|issue)|MTU|SNAT\s+port|NAT\s+(gateway|debug|issue)|Reachability\s+Analyzer)/i },
    { domain: "Virtual WAN / SD-WAN", prefix: "vwan", trigger: /\b(Virtual\s+WAN|vWAN|VWAN|routing\s+intent|secured\s+hub|SD[-\s]?WAN|inter[-\s]?hub|vWAN\s+hub)/i },
    { domain: "Network Monitoring", prefix: "nmon", trigger: /\b(network\s+monitor|Connection\s+Monitor|traffic\s+analytics|flow\s+log|network\s+(alert|dashboard|baseline|observ)|NSG\s+flow|VPC\s+flow|network\s+metric)/i },
    { domain: "Multi-Cloud Networking", prefix: "mcn", trigger: /\b(multi[-\s]?cloud\s+(network|connect|transit)|cross[-\s]?cloud|cloud[-\s]?to[-\s]?cloud|transit\s+(architecture|design)|cloud\s+interconnect\s+design|service\s+mapping\s+(across|between)\s+cloud)/i },
    { domain: "Network Pricing", prefix: "price", trigger: /\b(pric(e|ing)|cost\s+(estimat|compar|analy|optim|break)|egress\s+cost|data\s+transfer\s+cost|TCO|total\s+cost|network\s+cost|billing|budget|monthly\s+cost|how\s+much\s+(does|will|is)|cheaper|expensive|save\s+money|cost\s+saving|right[-\s]?siz)/i },
    { domain: "IaC Generator", prefix: "iac", trigger: /\b(bicep|terraform|arm\s+template|ansible|infra(structure)?[-\s]+(as[-\s]+code|code)|IaC|generate\s+(bicep|terraform|arm|ansible)|network\s+deployment\s+(template|code)|deploy\s+network(ing)?\s+(template|code))/i },
    { domain: "Container Networking", prefix: "cnet", trigger: /\b(CNI|container\s+network|kubernetes\s+network|k8s\s+network|network\s+polic(y|ies)|service\s+mesh|istio|linkerd|cilium|calico|ingress\s+controller|Gateway\s+API|pod[-\s]+(to[-\s]+pod|network|cidr)|cluster\s+mesh|AKS\s+network|EKS\s+network|GKE\s+network)/i },
    { domain: "CDN & Edge Networking", prefix: "cdn", trigger: /\b(CDN|content\s+delivery|Front\s+Door|CloudFront|Cloud\s+CDN|edge\s+(network|routing|compute)|cache\s+(optim|strateg|key|purg)|origin\s+(shield|group|failover)|Anycast|POP\s+(location|select)|WAF\s+at\s+edge)/i },
    { domain: "Network Automation & GitOps", prefix: "nauto", trigger: /\b(network\s+automat|GitOps\s+network|CI[\s/]?CD\s+network|pipeline\s+network|drift\s+detect|policy[-\s]+as[-\s]+code|network\s+testing|network\s+rollback|terraform\s+(pipeline|ci|automation)|bicep\s+(pipeline|ci|automation))/i },
    { domain: "SASE / SSE", prefix: "sase", trigger: /\b(SASE|SSE|zero\s+trust\s+network|ZTNA|secure\s+web\s+gateway|SWG|CASB|cloud\s+access\s+security|FWaaS|Prisma\s+Access|Netskope|security\s+service\s+edge|private\s+access|internet\s+access\s+gateway)/i },
    { domain: "Network Capacity Planning", prefix: "ncap", trigger: /\b(capacity\s+plan|bandwidth\s+forecast|gateway\s+siz(e|ing)|throughput\s+calc|network\s+scalab|growth\s+model|network\s+limit|subscription\s+limit|scale\s+limit|network\s+capacity)/i },
    { domain: "IPv6 Migration", prefix: "ipv6", trigger: /\b(IPv6|dual[-\s]?stack|NAT64|DNS64|464XLAT|IPv6\s+(migrat|transition|address|compat)|SLAAC|GUA|ULA|link[-\s]?local\s+address)/i },
];

// ── Build capabilities summary ─────────────────────────────────────────

function buildCapabilitiesSummary() {
    return `# Cloud Networking — Available Specialists

| # | Domain | Prefix | Role Tool | Orchestrator |
|---|--------|--------|-----------|-------------|
| 1 | VNet/Subnet Architecture | vnet_ | vnet_role | vnet_orchestrate |
| 2 | Firewall Engineering | fw_ | fw_role | fw_orchestrate |
| 3 | Load Balancing | lb_ | lb_role | lb_orchestrate |
| 4 | DNS | dns_ | dns_role | dns_orchestrate |
| 5 | Private Link / Endpoints | pl_ | pl_role | pl_orchestrate |
| 6 | Hybrid Connectivity | hyb_ | hyb_role | hyb_orchestrate |
| 7 | Network Security | nsec_ | nsec_role | nsec_orchestrate |
| 8 | Network Troubleshooting | ntsh_ | ntsh_role | ntsh_orchestrate |
| 9 | Virtual WAN / SD-WAN | vwan_ | vwan_role | vwan_orchestrate |
| 10 | Network Monitoring | nmon_ | nmon_role | nmon_orchestrate |
| 11 | Multi-Cloud Networking | mcn_ | mcn_role | mcn_orchestrate |
| 12 | Network Pricing | price_ | price_role | price_orchestrate |
| 13 | IaC Generator | iac_ | iac_role | iac_orchestrate |
| 14 | Container Networking | cnet_ | cnet_role | cnet_orchestrate |
| 15 | CDN & Edge Networking | cdn_ | cdn_role | cdn_orchestrate |
| 16 | Network Automation & GitOps | nauto_ | nauto_role | nauto_orchestrate |
| 17 | SASE / SSE | sase_ | sase_role | sase_orchestrate |
| 18 | Network Capacity Planning | ncap_ | ncap_role | ncap_orchestrate |
| 19 | IPv6 Migration | ipv6_ | ipv6_role | ipv6_orchestrate |

## Firewall Vendor Coverage
Azure Firewall, AWS Network Firewall, GCP Cloud Firewall/Cloud Armor, Palo Alto (PAN-OS/Panorama/VM-Series/Prisma), Fortinet FortiGate (FortiOS/FortiManager), Check Point (R81+/SmartConsole/CloudGuard), Cisco ASA/FTD, Juniper SRX/vSRX, Zscaler (ZIA/ZPA), Sophos XG/XGS, OPNsense, pfSense, VyOS, iptables/nftables

## IaC Generator — Supported Tools
Bicep, Terraform (azurerm/aws/google), Ansible (azure.azcollection/amazon.aws/google.cloud), ARM Templates

## How to use
1. Call the **role tool** (e.g. \`vnet_role\`) to load the specialist.
2. Call \`*_orchestrate\` for step-by-step guidance.
3. Call individual \`*_skill_*\` tools as you work.
Use \`cn_route\` to find the right specialist for a query.`;
}

function routeQuery(query) {
    const matches = ROUTES.filter((r) => r.trigger.test(query));
    if (matches.length === 0) {
        return "No specialist matched. Call `cn_capabilities` for the full map.\nAvailable: " +
            ROUTES.map((r) => r.domain).join(", ");
    }
    const lines = [`Matched ${matches.length} specialist(s):\n`];
    for (const m of matches) {
        lines.push(`### ${m.domain}`);
        lines.push(`- Role: \`${m.prefix}_role\`  |  Orchestrate: \`${m.prefix}_orchestrate\``);
        lines.push("");
    }
    lines.push("**Next:** Call the role tool, then follow the orchestrator workflow.");
    return lines.join("\n");
}

// ── Register ALL tools ─────────────────────────────────────────────────

const tools = [
    // ── Discovery tools ──
    {
        name: "cn_capabilities",
        description: "Returns a structured map of all 19 cloud networking specialist extensions, their role tools, and available skills. Use when you need to discover what networking capabilities are available.",
        parameters: { type: "object", properties: {} },
        skipPermission: true,
        handler: async () => buildCapabilitiesSummary(),
    },
    {
        name: "cn_route",
        description: "Given a cloud networking query, returns the recommended specialist extension(s) to use along with the tools to call. Use when unsure which specialist handles a request.",
        parameters: {
            type: "object",
            properties: { query: { type: "string", description: "The user's networking query or task description" } },
            required: ["query"],
        },
        skipPermission: true,
        handler: async (args) => routeQuery(args.query),
    },

    // ── 1. VNet/Subnet Architect ──
    roleTool("vnet_role",
        "Load the vnet-architect agent role and workflow for virtual network design across Azure, AWS, and GCP. Call this first when handling network architecture requests.",
        roleLoader("vnet-architect")),
    orchestratorTool("vnet_orchestrate",
        "Return the orchestration prompt for the VNet Architect agent. Use for VNet/VPC design, hub-spoke, peering, address planning.",
        ORCHESTRATORS.vnet),
    skillTool("vnet_skill_address_planner", "Skill: IP address space planning — CIDR allocation, subnet sizing, supernetting, overlap avoidance across environments.",
        skillLoader("vnet-architect", "address-planner")),
    skillTool("vnet_skill_hub_spoke_design", "Skill: Hub-spoke topology design with peering, transit, and shared services.",
        skillLoader("vnet-architect", "hub-spoke-design")),
    skillTool("vnet_skill_peering_advisor", "Skill: VNet/VPC peering configuration, transitive routing analysis, peering limits.",
        skillLoader("vnet-architect", "peering-advisor")),
    skillTool("vnet_skill_subnet_calculator", "Skill: Subnet math — CIDR splits, available IPs, reserved addresses per cloud provider.",
        skillLoader("vnet-architect", "subnet-calculator")),
    skillTool("vnet_skill_network_diagram", "Skill: Generate Mermaid network topology diagrams from infrastructure descriptions. Always prefers official cloud-provider icons.",
        skillLoader("vnet-architect", "network-diagram")),
    skillTool("vnet_skill_excalidraw_diagram", "Skill: Generate Excalidraw (.excalidraw JSON) network topology diagrams from infrastructure descriptions. Always prefers official Azure/AWS/GCP icon libraries from libraries.excalidraw.com.",
        skillLoader("vnet-architect", "excalidraw-diagram")),
    skillTool("vnet_skill_drawio_diagram", "Skill: Generate draw.io (.drawio XML) network topology diagrams from infrastructure descriptions. Always prefers native cloud-provider stencils (mxgraph.azure2, mxgraph.aws4, mxgraph.gcp2).",
        skillLoader("vnet-architect", "drawio-diagram")),
    skillTool("vnet_skill_migration_planner", "Skill: Plan network migrations — on-prem to cloud, cloud-to-cloud address space.",
        skillLoader("vnet-architect", "migration-planner")),

    // ── 2. Firewall Engineer ──
    roleTool("fw_role",
        "Load the firewall-engineer agent role for multi-vendor firewall analysis. Covers 14 platforms including OPNsense, pfSense, VyOS, iptables. Call this first for any firewall request.",
        roleLoader("firewall-engineer")),
    orchestratorTool("fw_orchestrate",
        "Return the orchestration prompt for the Firewall Engineer agent. Use for firewall rule analysis, policy design, vendor migration, config generation.",
        ORCHESTRATORS.fw),
    skillTool("fw_skill_rule_audit", "Skill: Audit firewall rules for shadow rules, overly permissive entries, unused rules, hit-count analysis. Multi-vendor.",
        skillLoader("firewall-engineer", "rule-audit")),
    skillTool("fw_skill_policy_design", "Skill: Design firewall policies from requirements — zone-based, app-aware, or L3/L4. Multi-vendor.",
        skillLoader("firewall-engineer", "policy-design")),
    skillTool("fw_skill_vendor_migrate", "Skill: Migrate firewall rules between vendor platforms (e.g., PAN-OS → FortiGate, ASA → Azure Firewall).",
        skillLoader("firewall-engineer", "vendor-migrate")),
    skillTool("fw_skill_config_gen", "Skill: Generate vendor-specific firewall configuration from a policy intent description.",
        skillLoader("firewall-engineer", "config-gen")),
    skillTool("fw_skill_hardening_check", "Skill: Security hardening checklist per vendor best practices.",
        skillLoader("firewall-engineer", "hardening-check")),
    skillTool("fw_skill_ha_design", "Skill: Firewall high-availability design per vendor — active/passive, active/active, clustering.",
        skillLoader("firewall-engineer", "ha-design")),
    skillTool("fw_skill_log_analysis", "Skill: Parse and analyze firewall logs (syslog, CEF, LEEF) for security events.",
        skillLoader("firewall-engineer", "log-analysis")),
    skillTool("fw_skill_troubleshoot", "Skill: Troubleshoot firewall connectivity — packet flow, NAT, routing, policy lookup. Multi-vendor.",
        skillLoader("firewall-engineer", "troubleshoot")),
    skillTool("fw_skill_policy_test", "Skill: Validate firewall rules before/after deploy — vendor simulators (Azure FW Policy Analyzer, AWS NFW log test, PAN test-security-policy-match, FortiGate policy lookup, Cisco packet-tracer, Check Point fw monitor), log-driven shadow testing, automated rule-coverage test cases, pre-deployment checklist.",
        skillLoader("firewall-engineer", "policy-test")),

    // ── 3. Load Balancer ──
    roleTool("lb_role",
        "Load the load-balancer agent role for traffic distribution across all three clouds. Call this first for LB requests.",
        roleLoader("load-balancer")),
    orchestratorTool("lb_orchestrate",
        "Return the orchestration prompt for the Load Balancer agent. Use for LB selection, health probes, SSL offload, WAF, traffic routing.",
        ORCHESTRATORS.lb),
    skillTool("lb_skill_lb_selector", "Skill: Recommend the right LB type (L4 vs L7, regional vs global, internal vs public) based on requirements.",
        skillLoader("load-balancer", "lb-selector")),
    skillTool("lb_skill_health_probe_design", "Skill: Design health probe strategies — intervals, thresholds, custom probes, grace periods.",
        skillLoader("load-balancer", "health-probe-design")),
    skillTool("lb_skill_ssl_offload", "Skill: TLS/SSL termination design — cert management, cipher suites, end-to-end encryption.",
        skillLoader("load-balancer", "ssl-offload")),
    skillTool("lb_skill_waf_rules", "Skill: WAF rule configuration — OWASP rulesets, custom rules, exclusions, tuning.",
        skillLoader("load-balancer", "waf-rules")),
    skillTool("lb_skill_traffic_routing", "Skill: Traffic routing methods — weighted, priority, geographic, latency-based, session affinity.",
        skillLoader("load-balancer", "traffic-routing")),
    skillTool("lb_skill_troubleshoot", "Skill: Troubleshoot LB issues — backend health, asymmetric routing, SNAT exhaustion, 502/504 errors.",
        skillLoader("load-balancer", "troubleshoot")),
    skillTool("lb_skill_tls_cert_mgmt", "Skill: TLS certificate lifecycle for load balancers — cert sources (managed, ACME, public/private CA), storage (Key Vault / ACM / Secret Manager / cert-manager), per-LB deployment, SNI/ALPN strategy, rotation, monitoring, emergency revocation.",
        skillLoader("load-balancer", "tls-cert-mgmt")),

    // ── 4. DNS Specialist ──
    roleTool("dns_role",
        "Load the dns-specialist agent role for DNS architecture across hybrid and multi-cloud environments. Call this first for DNS requests.",
        roleLoader("dns-specialist")),
    orchestratorTool("dns_orchestrate",
        "Return the orchestration prompt for the DNS Specialist agent. Use for DNS zone design, resolver config, record audits, migrations.",
        ORCHESTRATORS.dns),
    skillTool("dns_skill_zone_design", "Skill: DNS zone architecture — public vs private, split-horizon, zone delegation.",
        skillLoader("dns-specialist", "zone-design")),
    skillTool("dns_skill_resolver_design", "Skill: DNS resolver/forwarder topology — conditional forwarding, DNS Private Resolver, Route 53 Resolver.",
        skillLoader("dns-specialist", "resolver-design")),
    skillTool("dns_skill_record_audit", "Skill: Audit DNS records for stale entries, misconfigurations, TTL issues.",
        skillLoader("dns-specialist", "record-audit")),
    skillTool("dns_skill_migration_plan", "Skill: Plan DNS migrations — zone transfers, cutover strategies, TTL lowering.",
        skillLoader("dns-specialist", "migration-plan")),
    skillTool("dns_skill_troubleshoot", "Skill: Troubleshoot DNS resolution — nslookup/dig analysis, forwarding chain tracing.",
        skillLoader("dns-specialist", "troubleshoot")),
    skillTool("dns_skill_dnssec_design", "Skill: DNSSEC end-to-end design — algorithm selection (ECDSA P-256), KSK/ZSK/CSK, signing automation, DS-record delegation, NSEC3 parameters, key rollover (pre-publish and double-DS), monitoring, emergency rollback. Covers Azure DNS, Route 53, Cloud DNS, BIND.",
        skillLoader("dns-specialist", "dnssec-design")),

    // ── 5. Private Link Engineer ──
    roleTool("pl_role",
        "Load the private-link agent role for private connectivity to PaaS/SaaS services. Call this first for Private Link/Endpoint requests.",
        roleLoader("private-link")),
    orchestratorTool("pl_orchestrate",
        "Return the orchestration prompt for the Private Link Engineer agent. Use for private endpoint design, DNS integration, service exposure.",
        ORCHESTRATORS.pl),
    skillTool("pl_skill_endpoint_design", "Skill: Private endpoint architecture — subnet placement, DNS integration, approval workflows.",
        skillLoader("private-link", "endpoint-design")),
    skillTool("pl_skill_dns_integration", "Skill: Private DNS zone configuration for private endpoints — zone linking, A record management.",
        skillLoader("private-link", "dns-integration")),
    skillTool("pl_skill_service_exposure", "Skill: Expose services via Private Link Service / AWS PrivateLink / GCP PSC.",
        skillLoader("private-link", "service-exposure")),
    skillTool("pl_skill_security_review", "Skill: Review private endpoint security — NSG on PE subnets, network policies, access controls.",
        skillLoader("private-link", "security-review")),
    skillTool("pl_skill_troubleshoot", "Skill: Troubleshoot PE connectivity — DNS resolution, NSG blocks, approval state.",
        skillLoader("private-link", "troubleshoot")),

    // ── 6. Hybrid Connectivity ──
    roleTool("hyb_role",
        "Load the hybrid-connectivity agent role for hybrid and cross-premises networking. Call this first for VPN/ExpressRoute/Direct Connect requests.",
        roleLoader("hybrid-connectivity")),
    orchestratorTool("hyb_orchestrate",
        "Return the orchestration prompt for the Hybrid Connectivity agent. Use for VPN, ExpressRoute, Direct Connect, Cloud Interconnect design.",
        ORCHESTRATORS.hyb),
    skillTool("hyb_skill_vpn_design", "Skill: VPN gateway design — S2S, P2S, IKEv2/OpenVPN, BGP, active-active, custom IPsec policies.",
        skillLoader("hybrid-connectivity", "vpn-design")),
    skillTool("hyb_skill_expressroute_design", "Skill: ExpressRoute / Direct Connect / Cloud Interconnect circuit design, peering, and routing.",
        skillLoader("hybrid-connectivity", "expressroute-design")),
    skillTool("hyb_skill_bandwidth_calc", "Skill: Bandwidth planning — circuit sizing, aggregation, QoS, and cost estimation.",
        skillLoader("hybrid-connectivity", "bandwidth-calc")),
    skillTool("hyb_skill_routing_design", "Skill: BGP routing design — AS path manipulation, route filters, communities, local preference.",
        skillLoader("hybrid-connectivity", "routing-design")),
    skillTool("hyb_skill_failover_design", "Skill: Redundancy and failover — dual circuits, VPN backup, BFD, fast convergence.",
        skillLoader("hybrid-connectivity", "failover-design")),
    skillTool("hyb_skill_troubleshoot", "Skill: Troubleshoot hybrid connectivity — BGP neighbor state, tunnel status, MTU issues, asymmetric routing.",
        skillLoader("hybrid-connectivity", "troubleshoot")),
    skillTool("hyb_skill_bgp_design", "Skill: Dedicated BGP design for cloud hybrid — ASN allocation, prefix/AS-PATH filters, attribute manipulation (Local-Pref, prepend, MED, communities), multi-circuit active/active and active/passive, BFD, convergence tuning, cloud-specific gotchas (Azure ExpressRoute/VPN, AWS DX/VPN, GCP Cloud Router).",
        skillLoader("hybrid-connectivity", "bgp-design")),

    // ── 7. Network Security ──
    roleTool("nsec_role",
        "Load the network-security agent role for security posture and segmentation. Call this first for NSG/DDoS/segmentation requests.",
        roleLoader("network-security")),
    orchestratorTool("nsec_orchestrate",
        "Return the orchestration prompt for the Network Security agent. Use for NSG audits, segmentation, DDoS, compliance checks.",
        ORCHESTRATORS.nsec),
    skillTool("nsec_skill_nsg_audit", "Skill: Audit NSG/Security Group rules — overly permissive, unused, conflicting, priority gaps.",
        skillLoader("network-security", "nsg-audit")),
    skillTool("nsec_skill_segmentation_design", "Skill: Network segmentation strategy — micro-segmentation, zero-trust network access.",
        skillLoader("network-security", "segmentation-design")),
    skillTool("nsec_skill_ddos_design", "Skill: DDoS protection design — Azure DDoS Protection, AWS Shield, GCP Cloud Armor.",
        skillLoader("network-security", "ddos-design")),
    skillTool("nsec_skill_flow_analysis", "Skill: Analyze NSG/VPC flow logs for security patterns, anomalies, top talkers.",
        skillLoader("network-security", "flow-analysis")),
    skillTool("nsec_skill_compliance_check", "Skill: Check network config against compliance frameworks (CIS, NIST, PCI-DSS network controls).",
        skillLoader("network-security", "compliance-check")),
    skillTool("nsec_skill_troubleshoot", "Skill: Troubleshoot network security — blocked traffic, effective rules, IP flow verify.",
        skillLoader("network-security", "troubleshoot")),
    skillTool("nsec_skill_zero_trust_architecture", "Skill: Zero Trust networking architecture — NIST 800-207 / CISA ZTMM alignment, seven pillars, PEP/PDP placement, identity-aware access, microsegmentation, east-west encryption, egress control, continuous verification, workload identity (SPIFFE), threat model, anti-patterns.",
        skillLoader("network-security", "zero-trust-architecture")),
    skillTool("nsec_skill_waf_policy_design", "Skill: Cross-cloud WAF policy design — five-layer model (managed rules, custom rules, rate limits, bot management, geo/IP filters), Detect→Prevent rollout, OWASP CRS tuning, false-positive exclusions, integration with CDN/DDoS/API gateway. Covers Azure WAF, AWS WAFv2, GCP Cloud Armor, Cloudflare, F5, Imperva.",
        skillLoader("network-security", "waf-policy-design")),

    // ── 8. Network Troubleshooter ──
    roleTool("ntsh_role",
        "Load the network-troubleshooter agent role for diagnostics and debugging. Call this first for any connectivity/latency/routing issue.",
        roleLoader("network-troubleshooter")),
    orchestratorTool("ntsh_orchestrate",
        "Return the orchestration prompt for the Network Troubleshooter agent. Use for connectivity tests, packet captures, routing debug.",
        ORCHESTRATORS.ntsh),
    skillTool("ntsh_skill_connectivity_test", "Skill: Connectivity testing strategy — TCP/ICMP probes, traceroute, Network Watcher tools.",
        skillLoader("network-troubleshooter", "connectivity-test")),
    skillTool("ntsh_skill_packet_capture", "Skill: Packet capture mechanics — how to capture (Azure Network Watcher, AWS VPC Traffic Mirroring, GCP Packet Mirroring, tcpdump), capture filters, where to tap, dual-point captures. Pair with ntsh_skill_pcap_analysis for analysis of the resulting file.",
        skillLoader("network-troubleshooter", "packet-capture")),
    skillTool("ntsh_skill_pcap_analysis", "Skill: Deep PCAP analysis with Wireshark and tshark — tshark cheatsheet, Statistics & Expert Info workflows, TCP/TLS/DNS/HTTP diagnostic playbooks, dual-point merging, decryption (TLS keylog, IPsec, WireGuard), anonymization, cloud-source gotchas (Azure NW, AWS VPC Mirroring, GCP Mirroring, container netns).",
        skillLoader("network-troubleshooter", "pcap-analysis")),
    skillTool("ntsh_skill_latency_analysis", "Skill: Latency troubleshooting — hop-by-hop analysis, RTT baselines, jitter measurement.",
        skillLoader("network-troubleshooter", "latency-analysis")),
    skillTool("ntsh_skill_routing_debug", "Skill: Routing table analysis — effective routes, UDR conflicts, BGP route propagation.",
        skillLoader("network-troubleshooter", "routing-debug")),
    skillTool("ntsh_skill_nat_debug", "Skill: NAT troubleshooting — SNAT port exhaustion, DNAT rules, NAT gateway logs.",
        skillLoader("network-troubleshooter", "nat-debug")),
    skillTool("ntsh_skill_mtu_path_discovery", "Skill: MTU/MSS troubleshooting — path MTU discovery, fragmentation, jumbo frames.",
        skillLoader("network-troubleshooter", "mtu-path-discovery")),
    skillTool("ntsh_skill_tls_handshake_debug", "Skill: TLS handshake debugging — TLS alert code decoding (40, 42, 48, 51, 112, 116, 120), openssl s_client / testssl.sh / nmap workflows, cert chain validation, SNI/ALPN/mTLS failure patterns, OCSP stapling, clock skew, middlebox interception detection, decryption for forensics.",
        skillLoader("network-troubleshooter", "tls-handshake-debug")),

    // ── 9. Virtual WAN / SD-WAN ──
    roleTool("vwan_role",
        "Load the vwan-sdwan agent role for Azure Virtual WAN and SD-WAN integration. Call this first for vWAN/SD-WAN requests.",
        roleLoader("vwan-sdwan")),
    orchestratorTool("vwan_orchestrate",
        "Return the orchestration prompt for the Virtual WAN/SD-WAN agent. Use for vWAN design, routing intent, NVA integration.",
        ORCHESTRATORS.vwan),
    skillTool("vwan_skill_vwan_design", "Skill: Virtual WAN topology design — hubs, connections, secured hubs, inter-hub routing.",
        skillLoader("vwan-sdwan", "vwan-design")),
    skillTool("vwan_skill_routing_intent", "Skill: Routing intent and routing policies — internet traffic, private traffic, inter-hub.",
        skillLoader("vwan-sdwan", "routing-intent")),
    skillTool("vwan_skill_nva_integration", "Skill: NVA integration in vWAN — BGP peering, managed appliances, SD-WAN partners.",
        skillLoader("vwan-sdwan", "nva-integration")),
    skillTool("vwan_skill_branch_connectivity", "Skill: Branch connectivity — S2S VPN, P2S, ExpressRoute to vWAN.",
        skillLoader("vwan-sdwan", "branch-connectivity")),
    skillTool("vwan_skill_troubleshoot", "Skill: Troubleshoot vWAN — effective routes, connection state, hub routing.",
        skillLoader("vwan-sdwan", "troubleshoot")),
    skillTool("vwan_skill_secured_vhub_design", "Skill: Azure Secured Virtual Hub design — when to use vs hub-spoke+NVA, routing intent (internet/private/both), Azure Firewall vs partner NVA SKU selection, rule set design, forced-tunneling, HA & cross-region, observability, cost, common pitfalls (rogue peerings, Private Endpoint inspection).",
        skillLoader("vwan-sdwan", "secured-vhub-design")),

    // ── 10. Network Monitor ──
    roleTool("nmon_role",
        "Load the network-monitor agent role for observability and monitoring. Call this first for flow logs, traffic analytics, alerting requests.",
        roleLoader("network-monitor")),
    orchestratorTool("nmon_orchestrate",
        "Return the orchestration prompt for the Network Monitor agent. Use for flow logs, traffic analytics, connection monitors, dashboards.",
        ORCHESTRATORS.nmon),
    skillTool("nmon_skill_flow_log_setup", "Skill: Flow log configuration — NSG flow logs, VPC flow logs, storage/Log Analytics setup.",
        skillLoader("network-monitor", "flow-log-setup")),
    skillTool("nmon_skill_traffic_analytics", "Skill: Traffic analytics setup and query — top talkers, geo distribution, malicious IPs.",
        skillLoader("network-monitor", "traffic-analytics")),
    skillTool("nmon_skill_connection_monitor", "Skill: Connection monitor design — test groups, endpoints, alerting thresholds.",
        skillLoader("network-monitor", "connection-monitor")),
    skillTool("nmon_skill_synthetic_monitoring", "Skill: Proactive synthetic monitoring — Azure Connection Monitor, App Insights availability tests, AWS CloudWatch Synthetics, GCP Uptime Checks, Blackbox Exporter + Prometheus, global probe vendors. Probe design principles, retries/multi-region thresholds, SLO/SLI integration, dashboards, anti-patterns.",
        skillLoader("network-monitor", "synthetic-monitoring")),
    skillTool("nmon_skill_alert_design", "Skill: Network alerting strategy — metric alerts, log alerts, action groups, escalation.",
        skillLoader("network-monitor", "alert-design")),
    skillTool("nmon_skill_dashboard_build", "Skill: Network monitoring dashboard — KQL queries, Azure Monitor workbooks, CloudWatch.",
        skillLoader("network-monitor", "dashboard-build")),
    skillTool("nmon_skill_baseline_analysis", "Skill: Network baseline analysis — normal traffic patterns, anomaly detection.",
        skillLoader("network-monitor", "baseline-analysis")),

    // ── 11. Multi-Cloud Networking ──
    roleTool("mcn_role",
        "Load the multi-cloud-net agent role for cross-cloud and multi-cloud networking. Call this first for multi-cloud connectivity requests.",
        roleLoader("multi-cloud-net")),
    orchestratorTool("mcn_orchestrate",
        "Return the orchestration prompt for the Multi-Cloud Networking agent. Use for cross-cloud transit, addressing, service mapping.",
        ORCHESTRATORS.mcn),
    skillTool("mcn_skill_transit_design", "Skill: Multi-cloud transit architecture — VPN mesh, cloud-native interconnects, NVA transit.",
        skillLoader("multi-cloud-net", "transit-design")),
    skillTool("mcn_skill_addressing_plan", "Skill: Cross-cloud IP address plan — non-overlapping CIDR, summarization, NAT strategies.",
        skillLoader("multi-cloud-net", "addressing-plan")),
    skillTool("mcn_skill_service_mapping", "Skill: Map networking services across clouds (Azure VNet ↔ AWS VPC ↔ GCP VPC).",
        skillLoader("multi-cloud-net", "service-mapping")),
    skillTool("mcn_skill_latency_optimization", "Skill: Cross-cloud latency optimization — peering locations, backbone routing, CDN.",
        skillLoader("multi-cloud-net", "latency-optimization")),
    skillTool("mcn_skill_cost_comparison", "Skill: Network cost comparison across clouds — egress, peering, VPN, interconnect pricing.",
        skillLoader("multi-cloud-net", "cost-comparison")),

    // ── 12. Pricing Analyst ──
    roleTool("price_role",
        "Load the pricing-analyst agent role for network cost estimation and optimization across Azure, AWS, and GCP. Call this first for any pricing or cost question.",
        roleLoader("pricing-analyst")),
    orchestratorTool("price_orchestrate",
        "Return the orchestration prompt for the Pricing Analyst agent. Use for cost estimation, pricing comparison, egress calculation, cost optimization.",
        ORCHESTRATORS.price),
    skillTool("price_skill_egress_calc", "Skill: Data transfer and egress cost calculation across Azure, AWS, and GCP — tiered pricing, inter-region, peering costs.",
        skillLoader("pricing-analyst", "egress-calc")),
    skillTool("price_skill_egress_architecture", "Skill: Architectural patterns to structurally reduce egress cost — PrivateLink/Gateway Endpoints, CDN offload, regional pinning, cross-AZ minimization, dedicated interconnects, egress-free storage tiers, compression/batching, multi-cloud peering exchanges, NAT GW tax mitigation, commit discounts. Break-even modeling and review checklist.",
        skillLoader("pricing-analyst", "egress-architecture")),
    skillTool("price_skill_vpn_pricing", "Skill: VPN gateway pricing comparison — per-hour costs, tunnel limits, data transfer charges across all three clouds.",
        skillLoader("pricing-analyst", "vpn-pricing")),
    skillTool("price_skill_circuit_pricing", "Skill: Dedicated circuit pricing — ExpressRoute, Direct Connect, Cloud Interconnect fees, break-even analysis vs VPN.",
        skillLoader("pricing-analyst", "circuit-pricing")),
    skillTool("price_skill_lb_pricing", "Skill: Load balancer pricing — Azure LB/AppGW/Front Door, AWS ALB/NLB/GLB, GCP LB cost structures.",
        skillLoader("pricing-analyst", "lb-pricing")),
    skillTool("price_skill_firewall_pricing", "Skill: Firewall pricing — Azure Firewall tiers, AWS Network Firewall, GCP Cloud Armor, NVA marketplace costs.",
        skillLoader("pricing-analyst", "firewall-pricing")),
    skillTool("price_skill_cost_optimizer", "Skill: Network cost optimization — reduce egress, right-size gateways, reserved capacity, architectural patterns to save.",
        skillLoader("pricing-analyst", "cost-optimizer")),
    skillTool("price_skill_price_compare", "Skill: Cross-cloud network pricing comparison — side-by-side tables for equivalent services, workload scenario costs.",
        skillLoader("pricing-analyst", "price-compare")),

    // ── 13. IaC Generator ──
    roleTool("iac_role",
        "Load the iac-generator agent role for producing Infrastructure-as-Code templates for networking resources. Call this first for any Bicep, Terraform, Ansible, or ARM template request.",
        roleLoader("iac-generator")),
    orchestratorTool("iac_orchestrate",
        "Return the orchestration prompt for the IaC Generator agent. Use for generating deployment code (Bicep, Terraform, Ansible, ARM) for networking infrastructure.",
        ORCHESTRATORS.iac),
    skillTool("iac_skill_bicep_gen", "Skill: Generate Azure Bicep templates for networking resources — VNets, firewalls, VPN gateways, private endpoints, NSGs, route tables.",
        skillLoader("iac-generator", "bicep-gen")),
    skillTool("iac_skill_terraform_gen", "Skill: Generate Terraform configurations for networking across Azure (azurerm), AWS (aws), and GCP (google) providers.",
        skillLoader("iac-generator", "terraform-gen")),
    skillTool("iac_skill_ansible_gen", "Skill: Generate Ansible playbooks for network automation across Azure, AWS, and GCP using official collections.",
        skillLoader("iac-generator", "ansible-gen")),
    skillTool("iac_skill_arm_gen", "Skill: Generate ARM JSON templates for Azure networking resources with parameter files and linked template patterns.",
        skillLoader("iac-generator", "arm-gen")),

    // ── 14. Container Networking ──
    roleTool("cnet_role",
        "Load the container-networking agent role for Kubernetes/container networking across AKS, EKS, and GKE. Call this first for any K8s networking request.",
        roleLoader("container-networking")),
    orchestratorTool("cnet_orchestrate",
        "Return the orchestration prompt for the Container Networking agent. Use for CNI, network policies, service mesh, ingress, multi-cluster networking.",
        ORCHESTRATORS.cnet),
    skillTool("cnet_skill_cni_selection", "Skill: CNI plugin comparison and selection — Azure CNI, Calico, Cilium, Flannel, WeaveNet. Decision matrix for AKS/EKS/GKE.",
        skillLoader("container-networking", "cni-selection")),
    skillTool("cnet_skill_network_policy", "Skill: Kubernetes network policies — native, Calico, Cilium. Namespace isolation, pod-level segmentation.",
        skillLoader("container-networking", "network-policy")),
    skillTool("cnet_skill_service_mesh", "Skill: Service mesh design — Istio, Linkerd. mTLS, traffic splitting, observability, ambient vs sidecar.",
        skillLoader("container-networking", "service-mesh")),
    skillTool("cnet_skill_ingress_design", "Skill: Ingress and Gateway API — NGINX, Traefik, AGIC, ALB Controller. TLS termination, path/host routing.",
        skillLoader("container-networking", "ingress-design")),
    skillTool("cnet_skill_cross_cluster", "Skill: Multi-cluster networking — Submariner, ClusterMesh, Istio multi-cluster, Fleet Manager.",
        skillLoader("container-networking", "cross-cluster")),
    skillTool("cnet_skill_troubleshoot", "Skill: Container networking troubleshooting — pod connectivity, CoreDNS, CNI failures, IP exhaustion, sidecar issues.",
        skillLoader("container-networking", "troubleshoot")),

    // ── 15. CDN & Edge Networking ──
    roleTool("cdn_role",
        "Load the cdn-edge agent role for CDN architecture and edge networking. Call this first for CDN, caching, or edge routing requests.",
        roleLoader("cdn-edge")),
    orchestratorTool("cdn_orchestrate",
        "Return the orchestration prompt for the CDN & Edge agent. Use for CDN design, edge routing, caching, and WAF at edge.",
        ORCHESTRATORS.cdn),
    skillTool("cdn_skill_cdn_design", "Skill: CDN architecture — Azure Front Door, CloudFront, Cloud CDN. Origins, failover, private origins, HTTP/3.",
        skillLoader("cdn-edge", "cdn-design")),
    skillTool("cdn_skill_edge_routing", "Skill: Edge routing — Anycast, geo-routing, latency-based, edge compute (Rules Engine, Lambda@Edge, CloudFront Functions).",
        skillLoader("cdn-edge", "edge-routing")),
    skillTool("cdn_skill_cache_optimization", "Skill: Cache optimization — cache keys, TTL strategies, purge patterns, compression, streaming optimization.",
        skillLoader("cdn-edge", "cache-optimization")),
    skillTool("cdn_skill_waf_edge", "Skill: Security at the edge — WAF policies, bot management, rate limiting, DDoS at CDN, geo-blocking.",
        skillLoader("cdn-edge", "waf-edge")),
    skillTool("cdn_skill_troubleshoot", "Skill: CDN troubleshooting — cache miss analysis, origin health, TLS issues, latency debugging, purge failures.",
        skillLoader("cdn-edge", "troubleshoot")),

    // ── 16. Network Automation & GitOps ──
    roleTool("nauto_role",
        "Load the network-automation agent role for CI/CD, GitOps, and automation of network infrastructure. Call this first for network automation requests.",
        roleLoader("network-automation")),
    orchestratorTool("nauto_orchestrate",
        "Return the orchestration prompt for the Network Automation agent. Use for pipelines, drift detection, policy-as-code, testing, rollback.",
        ORCHESTRATORS.nauto),
    skillTool("nauto_skill_pipeline_design", "Skill: CI/CD pipeline design for network IaC — GitHub Actions, Azure DevOps, stages, approvals, secrets.",
        skillLoader("network-automation", "pipeline-design")),
    skillTool("nauto_skill_drift_detection", "Skill: Configuration drift detection — Terraform state drift, Resource Graph queries, AWS Config, remediation.",
        skillLoader("network-automation", "drift-detection")),
    skillTool("nauto_skill_policy_as_code", "Skill: Policy-as-code — Azure Policy, OPA/Rego, Checkov, tfsec. Enforce network governance pre-deployment.",
        skillLoader("network-automation", "policy-as-code")),
    skillTool("nauto_skill_testing", "Skill: Network config testing — Terratest, Pester, pytest, smoke tests, integration tests, chaos engineering.",
        skillLoader("network-automation", "testing")),
    skillTool("nauto_skill_rollback", "Skill: Rollback and change management — state rollback, blue-green, canary, blast radius control, validation gates.",
        skillLoader("network-automation", "rollback")),

    // ── 17. SASE / SSE ──
    roleTool("sase_role",
        "Load the sase-sse agent role for Secure Access Service Edge and Security Service Edge architecture. Call this first for SASE/ZTNA/SSE requests.",
        roleLoader("sase-sse")),
    orchestratorTool("sase_orchestrate",
        "Return the orchestration prompt for the SASE/SSE agent. Use for ZTNA, SWG, CASB, SD-WAN integration, vendor selection.",
        ORCHESTRATORS.sase),
    skillTool("sase_skill_architecture", "Skill: SASE/SSE architecture design — framework components, deployment models, migration from legacy VPN/proxy.",
        skillLoader("sase-sse", "architecture")),
    skillTool("sase_skill_ztna_design", "Skill: Zero Trust Network Access — identity-based access, app connectors, device posture, continuous trust.",
        skillLoader("sase-sse", "ztna-design")),
    skillTool("sase_skill_swg_casb", "Skill: Secure Web Gateway & CASB — URL filtering, TLS inspection, shadow IT, DLP, SaaS security posture.",
        skillLoader("sase-sse", "swg-casb")),
    skillTool("sase_skill_sdwan_integration", "Skill: SD-WAN with SASE integration — traffic steering, branch connectivity, QoS, vendor integrations.",
        skillLoader("sase-sse", "sdwan-integration")),
    skillTool("sase_skill_vendor_compare", "Skill: SASE/SSE vendor comparison — Zscaler, Palo Alto Prisma, Netskope, Cisco, Microsoft, Fortinet.",
        skillLoader("sase-sse", "vendor-compare")),

    // ── 18. Network Capacity Planning ──
    roleTool("ncap_role",
        "Load the capacity-planner agent role for network capacity planning and sizing. Call this first for bandwidth, sizing, or scalability requests.",
        roleLoader("capacity-planner")),
    orchestratorTool("ncap_orchestrate",
        "Return the orchestration prompt for the Network Capacity Planner agent. Use for bandwidth forecasting, sizing, throughput, scalability.",
        ORCHESTRATORS.ncap),
    skillTool("ncap_skill_bandwidth_forecast", "Skill: Bandwidth forecasting — traffic modeling, baseline establishment, growth projections, threshold alerts.",
        skillLoader("capacity-planner", "bandwidth-forecast")),
    skillTool("ncap_skill_gateway_sizing", "Skill: Gateway and service sizing — VPN GW SKUs, ExpressRoute, App Gateway capacity units, firewall throughput.",
        skillLoader("capacity-planner", "gateway-sizing")),
    skillTool("ncap_skill_throughput_calc", "Skill: Throughput calculations — TCP window/RTT, BDP, encryption overhead, multi-flow limits, SNAT ports.",
        skillLoader("capacity-planner", "throughput-calc")),
    skillTool("ncap_skill_scalability_design", "Skill: Scalability patterns — subscription/account limits, horizontal scaling, when to split architectures.",
        skillLoader("capacity-planner", "scalability-design")),
    skillTool("ncap_skill_growth_model", "Skill: Growth modeling — user/device projections, traffic amplification, seasonal spikes, budget justification.",
        skillLoader("capacity-planner", "growth-model")),

    // ── 19. IPv6 Migration ──
    roleTool("ipv6_role",
        "Load the ipv6-migration agent role for IPv6 transition and dual-stack networking. Call this first for any IPv6 request.",
        roleLoader("ipv6-migration")),
    orchestratorTool("ipv6_orchestrate",
        "Return the orchestration prompt for the IPv6 Migration agent. Use for dual-stack, transition planning, addressing, NAT64/DNS64.",
        ORCHESTRATORS.ipv6),
    skillTool("ipv6_skill_dual_stack", "Skill: Dual-stack design — Azure/AWS/GCP dual-stack VNets/VPCs, LB support, DNS (A+AAAA), application considerations.",
        skillLoader("ipv6-migration", "dual-stack")),
    skillTool("ipv6_skill_transition_plan", "Skill: IPv6 transition strategies — phased migration, support matrix per cloud, rollback, success criteria.",
        skillLoader("ipv6-migration", "transition-plan")),
    skillTool("ipv6_skill_addressing", "Skill: IPv6 addressing schemes — GUA, ULA, /48 per site convention, subnet allocation, cloud-specific constraints.",
        skillLoader("ipv6-migration", "addressing")),
    skillTool("ipv6_skill_compatibility", "Skill: IPv4/IPv6 compatibility — NAT64, DNS64, 464XLAT, SIIT. When to use each mechanism.",
        skillLoader("ipv6-migration", "compatibility")),
    skillTool("ipv6_skill_troubleshoot", "Skill: IPv6 troubleshooting — connectivity, ICMPv6, PMTUD, NDP, DNS resolution, firewall misconfigs.",
        skillLoader("ipv6-migration", "troubleshoot")),
];

// ── Register session ───────────────────────────────────────────────────

// Explicit mention pattern — users type `@cloud-networking ...` to engage the extension.
// Accepts a few common variations and is case-insensitive.
const MENTION_RE = /(^|\s)@cloud[-_]?networking\b/i;

const session = await joinSession({
    tools,
    hooks: {
        onUserPromptSubmitted: async (input) => {
            if (!input?.prompt) return;

            const mentioned = MENTION_RE.test(input.prompt);
            // Strip the @cloud-networking mention before scanning for specialist keywords
            const scanText = mentioned ? input.prompt.replace(MENTION_RE, " ") : input.prompt;
            const matches = ROUTES.filter((r) => r.trigger.test(scanText));

            // Only engage when the user explicitly mentions @cloud-networking,
            // OR when networking keywords clearly match a specialist.
            if (!mentioned && matches.length === 0) return;

            const header = mentioned
                ? `[cloud-networking] @cloud-networking invoked.`
                : `[cloud-networking] Detected networking intent.`;

            if (matches.length === 0) {
                // Mentioned but no specialist matched — engage the router automatically.
                return {
                    additionalContext:
                        `${header} No single specialist matched the request directly.\n\n` +
                        `Engage the routing flow now: silently call \`cn_route\` with the user's query ` +
                        `to pick the right specialist, then call that specialist's role tool, then its ` +
                        `orchestrator, then the relevant skills. If still ambiguous, call ` +
                        `\`cn_capabilities\` and ask the user which area to focus on.\n\n` +
                        `Do not list internal tool names to the user — respond in natural language.`,
                };
            }

            const guidance = matches
                .map((m) => `• **${m.domain}** — engage this specialist`)
                .join("\n");

            return {
                additionalContext:
                    `${header} Engage the following specialist(s):\n${guidance}\n\n` +
                    `For each matched specialist, silently call its role tool, then its ` +
                    `orchestrator, then the relevant skills to fulfil the user's request. ` +
                    `Respond to the user in natural language — do not list internal tool names.`,
            };
        },
    },
});

await session.log(
    "cloud-networking loaded — 19 specialists, 156 tools, standalone. Trigger with @cloud-networking",
);

// Fire-and-forget update check (throttled to once per 24h, opt-out via env var).
checkForUpdate(session);
