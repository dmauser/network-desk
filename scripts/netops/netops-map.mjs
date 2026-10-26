// NetOps skill map — which Network Desk specialist content backs each NetOps
// skill, and which runtime symptoms route to it.
//
// Single source of truth: specialist knowledge stays in
// extensions/network-desk/{registry.mjs,specialists/**}. build-netops.mjs copies
// the referenced role/sub-skill docs into plugins/netops/skills/<skill>/reference/
// (generated, drift-checked) and emits plugins/netops/agents/routing.json, which
// the investigator instructions, the evals router, and tests all consume.
//
// Symptom patterns must stay portable between JavaScript and Python `re`
// (use only \b, \s, \d, character classes, groups, alternation, ? * +).

export const NETOPS_PLUGIN = {
    name: "netops",
    version: "0.1.0",
    displayName: "NetOps — Network Operations for Azure SRE Agent (powered by Network Desk)",
    description:
        "NetOps — Network Operations for Azure SRE Agent (powered by Network Desk). Read-only Azure network " +
        "operations pack: ten skills (managed-scope enforcement, deterministic Live Report rendering, hybrid " +
        "VPN/ExpressRoute/BGP health, private endpoint + DNS validation, routing/asymmetry analysis, NSG/Azure " +
        "Firewall audit, exposure scan, SNAT/egress health, IP/gateway capacity forecast, flow-log insights), plus " +
        "an installer that adds the netops-investigator agent and scheduled tasks (a plugin install alone imports " +
        "only the skills). Remediation is emitted as scripts for a human to review and run; the agent executes no " +
        "Azure writes and needs no write RBAC.",
    marketplaceDescription:
        "Read-only Azure network operations for Azure SRE Agent (powered by Network Desk): hybrid/BGP health, " +
        "private endpoint DNS, routing, NSG/firewall audit, exposure, SNAT, IP capacity, and flow insights, with " +
        "managed-scope enforcement, an investigator agent, and scheduled tasks.",
};

// Order matters: it is the deterministic tie-break when two skills score equally.
export const NETOPS_SKILLS = {
    "netops-hybrid-health": {
        title: "Hybrid connectivity health (VPN / ExpressRoute / BGP)",
        sources: {
            hyb: ["troubleshoot", "bgp-design", "vpn-design", "expressroute-design", "failover-design"],
        },
        symptoms: [
            "\\bVPN\\b", "express\\s?route", "\\bER\\s+(circuit|gateway|connection)", "\\bBGP\\b",
            "\\btunnel", "\\bIPsec\\b", "\\bIKE(v1|v2)?\\b", "on[-\\s]?prem", "\\bbranch\\b",
            "site[-\\s]to[-\\s]site", "\\bS2S\\b", "learned\\s+routes?", "advertised\\s+routes?",
            "\\bflap", "\\bMSEE\\b", "hybrid\\s+connectivity", "gateway\\s+(disconnected|down)",
        ],
    },
    "netops-private-endpoint-dns": {
        title: "Private endpoint + private DNS validation",
        sources: {
            pl: ["troubleshoot", "dns-integration", "endpoint-design"],
            dns: ["troubleshoot", "resolver-design", "record-audit"],
        },
        symptoms: [
            "private\\s+endpoint", "private\\s?link", "privatelink\\.", "private\\s+DNS",
            "DNS\\s+(resolution|resolves?|lookup)", "\\bNXDOMAIN\\b", "resolv(es|ing)\\s+to\\s+(a\\s+)?public",
            "\\bnslookup\\b", "\\bdig\\b", "zone\\s+(group|link)", "virtual\\s+network\\s+link",
            "DNS\\s+(private\\s+)?resolver", "conditional\\s+forward", "PaaS\\s+(service\\s+)?(is\\s+)?unreachable",
        ],
    },
    "netops-routing-analyzer": {
        title: "Effective routes, UDRs, and asymmetric routing",
        sources: {
            ntsh: ["routing-debug", "connectivity-test"],
            vnet: ["peering-advisor", "hub-spoke-design"],
        },
        symptoms: [
            "\\bUDR", "route\\s+table", "effective\\s+routes?", "next[-\\s]?hop", "black[-\\s]?hol",
            "asymmetr", "\\bNVA\\b", "network\\s+virtual\\s+appliance", "return\\s+path",
            "forced\\s+tunnel", "0\\.0\\.0\\.0/0", "\\bpeering\\b", "hub[-\\s]?spoke", "spoke[-\\s]to[-\\s]spoke",
            "transit", "routing\\s+loop",
        ],
    },
    "netops-nsg-firewall-audit": {
        title: "NSG and Azure Firewall rule audit",
        sources: {
            nsec: ["nsg-audit", "compliance-check"],
            fw: ["rule-audit", "hardening-check", "log-analysis"],
        },
        symptoms: [
            "\\bNSGs?\\b", "network\\s+security\\s+group", "security\\s+rules?", "firewall\\s+(rule|policy|polic)",
            "azure\\s+firewall", "deny\\s+rule", "shadow(ed)?\\s+rule", "overly\\s+(broad|permissive)",
            "any[-\\s]?any", "rule\\s+audit", "blocked\\s+by\\s+(the\\s+)?(NSG|firewall)", "denied\\s+by",
        ],
    },
    "netops-exposure-scan": {
        title: "Internet exposure scan",
        sources: {
            nsec: ["nsg-audit", "waf-policy-design", "ddos-design", "zero-trust-architecture"],
        },
        symptoms: [
            "public\\s+IPs?", "internet[-\\s](exposed|facing|exposure)", "\\bexposure\\b", "open\\s+to\\s+(the\\s+)?internet",
            "public\\s?network\\s?access", "attack\\s+surface", "\\bWAF\\b", "\\bDDoS\\b",
            "(RDP|SSH)\\s+(open|exposed)", "\\b(3389|22)\\s+(open|exposed)",
        ],
    },
    "netops-snat-egress": {
        title: "SNAT port exhaustion and egress health",
        sources: {
            ntsh: ["nat-debug", "latency-analysis"],
            nmon: ["alert-design", "baseline-analysis"],
            lb: ["troubleshoot"],
        },
        symptoms: [
            "\\bSNAT\\b", "port\\s+exhaustion", "\\boutbound\\b", "\\begress\\b", "NAT\\s+gateway",
            "\\blatency\\b", "packet\\s+(drop|loss)", "dropped\\s+packets", "time[-\\s]?outs?",
            "intermittent", "connection\\s+(failures?|resets?)", "TCP\\s+reset",
        ],
    },
    "netops-ip-capacity": {
        title: "Subnet IP and gateway capacity forecast",
        sources: {
            ncap: ["gateway-sizing", "growth-model", "scalability-design"],
            vnet: ["address-planner", "subnet-calculator"],
        },
        symptoms: [
            "IP\\s+(address\\s+)?exhaust", "address\\s+space", "subnet\\s+(is\\s+)?full", "available\\s+IPs?",
            "out\\s+of\\s+(IP|addresses)", "\\bcapacity\\b", "\\bforecast", "gateway\\s+(throughput|capacity|sku)",
            "scale[-\\s]?out", "\\bheadroom\\b",
        ],
    },
    "netops-flow-insights": {
        title: "VNet/NSG flow logs and Traffic Analytics",
        sources: {
            nmon: ["flow-log-setup", "traffic-analytics", "baseline-analysis"],
            nsec: ["flow-analysis"],
        },
        symptoms: [
            "flow\\s+logs?", "traffic\\s+analytics", "top\\s+talkers?", "denied\\s+flows?", "\\bNTA[A-Za-z]+",
            "traffic\\s+pattern", "bandwidth\\s+usage", "telemetry\\s+gap", "missing\\s+(logs|telemetry)",
            "who\\s+is\\s+talking",
        ],
    },
};

// Utility skills that carry no specialist reference content.
export const NETOPS_UTILITY_SKILLS = ["netops-managed-scope", "netops-report-renderer"];
