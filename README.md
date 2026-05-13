# Cloud Networking

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js >= 18](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org/)

**Your cloud networking AI team for GitHub Copilot CLI.** 19 specialist agents covering VNet design, firewalls (14 vendors), load balancing, DNS, private connectivity, IaC generation, container networking, CDN/edge, SASE/SSE, and more — routed automatically.

---

### 📌 Table of Contents

| | Section | Description |
|---|---------|-------------|
| 🚀 | [Quick Start](#quick-start) | One-command install |
| 💡 | [What is Cloud Networking?](#what-is-cloud-networking) | Overview and key concepts |
| 👥 | [The Team](#the-team) | All 19 specialists at a glance |
| 📦 | [Installation](#installation) | 5 ways to install (npx user-level, npx project-level, npm, Copilot prompt, manual) |
| 🖥️ | [CLI Reference](#cli-reference) | `init`, `status`, `uninstall`, `--version` |
| ⚙️ | [How It Works](#how-it-works) | Architecture, routing, and workflow |
| 📝 | [Usage Examples](#usage-examples) | Example prompts for every specialist |
| 📂 | [Repository Structure](#repository-structure) | Full folder tree and conventions |
| 🔧 | [Troubleshooting](#troubleshooting) | Common issues and fixes |
| 📄 | [License](#license) | MIT |

---

## Quick Start

```bash
npx github:dmauser/cloud-networking init
```

That's it. Launch Copilot CLI with experimental mode (`copilot --experimental`) in any repo and start asking networking questions.

## What is Cloud Networking?

Cloud Networking gives you a coordinated team of network specialist agents through [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/about-copilot-cli). Describe what you need — VNet design, firewall rules, DNS troubleshooting, hybrid connectivity, IaC generation, container networking, SASE architecture — and the coordinator routes your request to the right specialist automatically.

Each specialist runs with its own domain expertise, guardrails, and workflow. The coordinator handles routing and multi-domain orchestration so you don't have to remember which tools to call.

> **Analysis only** — Cloud Networking produces designs, configurations, IaC templates, and analysis for human review. It generates deployment code but does not execute deployments, modify live firewalls, or make changes to production networks.

## The Team

| Specialist | Prefix | What They Do |
|-----------|--------|-------------|
| **VNet/Subnet Architect** | `vnet_` | VNet/VPC design, hub-spoke, peering, address planning, Mermaid diagrams |
| **Firewall Engineer** | `fw_` | Multi-vendor firewall rules, policies, migration, config gen (14 vendors) |
| **Load Balancer** | `lb_` | LB selection, health probes, SSL offload, WAF, traffic routing |
| **DNS Specialist** | `dns_` | DNS zones, resolvers, record audits, migration, troubleshooting |
| **Private Link Engineer** | `pl_` | Private endpoints, DNS integration, service exposure, security |
| **Hybrid Connectivity** | `hyb_` | VPN, ExpressRoute, Direct Connect, BGP, failover design |
| **Network Security** | `nsec_` | NSG audits, segmentation, DDoS, flow analysis, compliance |
| **Network Troubleshooter** | `ntsh_` | Connectivity tests, packet capture, latency, routing, NAT, MTU |
| **Virtual WAN / SD-WAN** | `vwan_` | vWAN design, routing intent, NVA integration, branch connectivity |
| **Network Monitor** | `nmon_` | Flow logs, traffic analytics, connection monitors, dashboards, alerts |
| **Multi-Cloud Networking** | `mcn_` | Cross-cloud transit, addressing, service mapping, cost comparison |
| **Pricing Analyst** | `price_` | Network cost estimation, egress calculation, pricing comparison, cost optimization |
| **IaC Generator** | `iac_` | Bicep, Terraform, Ansible, ARM templates for networking infrastructure |
| **Container Networking** | `cnet_` | CNI plugins, network policies, service mesh, ingress, multi-cluster (AKS/EKS/GKE) |
| **CDN & Edge Networking** | `cdn_` | Azure Front Door, CloudFront, Cloud CDN, edge routing, caching, WAF at edge |
| **Network Automation & GitOps** | `nauto_` | CI/CD pipelines, drift detection, policy-as-code, testing, rollback |
| **SASE / SSE** | `sase_` | ZTNA, SWG, CASB, FWaaS, SD-WAN integration, vendor comparison |
| **Network Capacity Planning** | `ncap_` | Bandwidth forecasting, gateway sizing, throughput calculations, growth modeling |
| **IPv6 Migration** | `ipv6_` | Dual-stack design, transition planning, addressing, NAT64/DNS64, troubleshooting |

### Firewall Vendors (14)

Azure Firewall · AWS Network Firewall · GCP Cloud Firewall / Cloud Armor · Palo Alto (PAN-OS / Panorama / VM-Series / Prisma) · Fortinet FortiGate (FortiOS / FortiManager) · Check Point (R81+ / SmartConsole / CloudGuard) · Cisco ASA / FTD · Juniper SRX / vSRX · Zscaler (ZIA / ZPA) · Sophos XG / XGS · OPNsense · pfSense · VyOS · iptables / nftables

## Installation

### Prerequisites

- [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/about-copilot-cli) installed and authenticated
- [Node.js 18+](https://nodejs.org/)
- **Experimental mode** (user-level install only) — enable with `copilot --experimental` or `/experimental` inside Copilot CLI. Not needed for project-level install (`init --project`)

### Option A — User-level install (recommended)

The fastest way to install globally. Extensions load in every repo but require **experimental mode**:

```bash
npx github:dmauser/cloud-networking init
```

Then launch Copilot with experimental mode:

```bash
copilot --experimental
```

This will:
1. Create `~/.copilot/extensions/cloud-networking/` if it doesn't exist
2. Copy the extension router and all 19 specialists
3. Remove any conflicting individual specialist extensions
4. Display a summary of what was installed

### Option B — Project-level install (no experimental mode needed)

Installs the extension into the current repo's `.github/extensions/` directory. Works without experimental mode, but only for this repo.

> **Important:** You must run this from inside a git repository. If you don't have one yet, run `git init` first.

```bash
# cd into your repo first
cd my-repo
npx github:dmauser/cloud-networking init --project
```

Then launch Copilot normally from the repo:

```bash
copilot
```

This will:
1. Create `.github/extensions/cloud-networking/` in the current repo
2. Copy the extension router and all 19 specialists
3. Add the extension directory to `.gitignore` (each developer runs init themselves)

### Option C — Global install via npm

If you prefer a persistent CLI command instead of `npx`:

```bash
npm install -g github:dmauser/cloud-networking

# User-level install (requires experimental mode)
cloud-networking init

# Or project-level install (no experimental mode needed)
cloud-networking init --project

# Now available as a command:
cloud-networking status
cloud-networking --version
```

### Option D — Install from inside Copilot CLI

Already have Copilot CLI open? You can install directly from the prompt — just ask Copilot to clone the repo and run the installer for you:

```
Clone https://github.com/dmauser/cloud-networking.git and run `node bin/cli.mjs init` from the cloned directory.
```

Or if you already cloned the repo and are inside it:

```
Run `node bin/cli.mjs init` to install the cloud-networking extensions.
```

Copilot will execute the commands, copy the extensions into `~/.copilot/extensions/cloud-networking/`, and confirm the result. After installation, restart Copilot CLI to load the new extensions, then verify with:

```
show me the cloud-networking capabilities
```

### Option E — Manual install (offline / corporate environments)

<details>
<summary>Click to expand manual steps</summary>

Use this if you're behind a corporate proxy or don't have access to npm/npx.

**Step 1 — Clone the repo:**

```bash
git clone https://github.com/dmauser/cloud-networking.git
cd cloud-networking
```

**Step 2 — Copy to your Copilot extensions directory:**

macOS / Linux:

```bash
mkdir -p ~/.copilot/extensions/cloud-networking
cp -r extensions/cloud-networking/* ~/.copilot/extensions/cloud-networking/
```

Windows (PowerShell):

```powershell
$dest = "$env:USERPROFILE\.copilot\extensions\cloud-networking"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path "extensions\cloud-networking\*" -Destination $dest -Recurse -Force
```

**Step 3 — Verify the files are in place:**

```bash
ls ~/.copilot/extensions/cloud-networking/
# Should show: extension.mjs  specialists/
```

</details>

### Verify installation

After any install method, check that everything is in place:

```bash
# If you used Option A or B:
npx github:dmauser/cloud-networking status

# Or launch Copilot CLI and ask:
copilot
> show me the cloud-networking capabilities
```

You should see all 19 specialists listed with their tools.

### Updating

To update to the latest version, re-run the install command. It safely replaces the existing installation:

```bash
npx github:dmauser/cloud-networking init
```

### Uninstall

```bash
# Using the CLI:
npx github:dmauser/cloud-networking uninstall

# Or manually:
# macOS / Linux
rm -rf ~/.copilot/extensions/cloud-networking
# Windows (PowerShell)
Remove-Item -Recurse -Force "$env:USERPROFILE\.copilot\extensions\cloud-networking"
```

## CLI Reference

The `cloud-networking` CLI manages installation of the Copilot extensions. You can run it via `npx` or install it globally.

| Command | Description |
|---------|-------------|
| `cloud-networking init` | Install/reinstall extensions to `~/.copilot/extensions/` |
| `cloud-networking init --project` | Install extensions to `.github/extensions/` in current repo |
| `cloud-networking status` | Check installation status and list available specialists |
| `cloud-networking uninstall` | Remove installed extensions |
| `cloud-networking help` | Show CLI help |

## How It Works

```
User prompt
    │
    ▼
Cloud Networking Extension (~/.copilot/extensions/cloud-networking/extension.mjs)
    │
    ├─ Auto-routing hook detects networking keywords
    │   └─ Injects routing context → "use fw_* tools for firewall config"
    │
    ├─ cn_capabilities → full map of all 19 specialists
    ├─ cn_route → explicit routing for any query
    │
    └─ Specialist extensions provide the actual tools
        ├─ vnet_role, vnet_orchestrate, vnet_skill_hub_spoke_design, ...
        ├─ fw_role, fw_orchestrate, fw_skill_config_gen, ...
        ├─ iac_role, iac_orchestrate, iac_skill_bicep_gen, ...
        └─ ntsh_role, ntsh_orchestrate, ntsh_skill_packet_capture, ...
```

### Typical workflow

Each specialist follows a consistent pattern:

1. **Load the role** — call `<prefix>_role` (e.g. `fw_role`) to load the specialist's persona and workflow
2. **Orchestrate** — call `<prefix>_orchestrate` for step-by-step guidance
3. **Run skills** — call individual `<prefix>_skill_*` tools to perform the work

You don't need to call these manually — just describe what you need and the routing hook handles it.

## Usage Examples

Just describe what you need in plain language — the router picks the right specialist automatically.

### 🏗️ VNet/Subnet Architect

```
Design a hub-spoke VNet topology for a 3-tier app with separate dev/staging/prod environments.
```
```
Plan an IP address scheme for 12 VNets across 3 Azure regions with no overlapping CIDRs.
```
```
Generate a Mermaid diagram of my current hub-spoke peering architecture.
```

### 🔥 Firewall Engineer

```
Generate Palo Alto PAN-OS rules to allow HTTPS from my app subnet to a backend API on port 8443.
```
```
Migrate these Cisco ASA ACLs to Azure Firewall policy rules.
```
```
Audit my FortiGate ruleset for shadowed, redundant, or overly permissive rules.
```

### ⚖️ Load Balancer

```
Which Azure load balancer should I use — Standard LB, App Gateway, or Front Door?
```
```
Design health probes for a multi-region API behind Azure Front Door.
```
```
Configure SSL offload on an Application Gateway with end-to-end TLS.
```

### 🌐 DNS Specialist

```
Design a private DNS zone architecture for 5 VNets with hub-spoke peering.
```
```
Audit my DNS records for stale entries, mismatched TTLs, and missing PTR records.
```
```
Troubleshoot — internal VMs can't resolve privatelink.blob.core.windows.net.
```

### 🔒 Private Link Engineer

```
Set up private endpoints for Azure SQL and Storage with proper DNS integration.
```
```
Review the security posture of my private endpoint configuration — any gaps?
```
```
Expose my internal API to a partner tenant using Private Link Service.
```

### 🔗 Hybrid Connectivity

```
Design a site-to-site VPN between Azure and our on-prem data center with BGP.
```
```
Plan an ExpressRoute circuit with Global Reach for US-East and West Europe.
```
```
Design a failover strategy: ExpressRoute primary, VPN backup with automatic failover.
```

### 🛡️ Network Security

```
Audit all NSGs in my subscription — flag any-any rules, unused NSGs, and overly broad ranges.
```
```
Design a micro-segmentation strategy for a PCI-DSS compliant environment.
```
```
Analyze NSG flow logs to identify top talkers and unexpected traffic patterns.
```

### 🔧 Network Troubleshooter

```
My VM in spoke-vnet-02 can't reach the database in hub-vnet — diagnose the connectivity path.
```
```
Run a packet capture on my NVA to debug why return traffic is being dropped.
```
```
Investigate high latency between my Azure VMs and on-prem servers — is it routing or MTU?
```

### 🌍 Virtual WAN / SD-WAN

```
Design a Virtual WAN topology for 20 branch offices across 3 regions.
```
```
Configure routing intent for internet breakout through Azure Firewall in my vWAN hub.
```
```
Integrate a Palo Alto NVA into my Virtual WAN hub for traffic inspection.
```

### 📊 Network Monitor

```
Set up NSG flow logs with Traffic Analytics for all my production VNets.
```
```
Build a monitoring dashboard for VPN gateway throughput, latency, and tunnel status.
```
```
Create alert rules for when ExpressRoute circuit utilization exceeds 80%.
```

### ☁️ Multi-Cloud Networking

```
Design a transit architecture connecting Azure, AWS, and GCP with consistent addressing.
```
```
Map equivalent networking services across Azure, AWS, and GCP for our migration plan.
```
```
Compare the cost of cross-cloud connectivity options: VPN vs dedicated interconnect vs SD-WAN.
```

### 💰 Pricing Analyst

```
How much will 5TB of monthly egress from Azure East US cost?
```
```
Compare VPN gateway costs across Azure, AWS, and GCP for 500 Mbps.
```
```
Should I use ExpressRoute or S2S VPN for 2 Gbps sustained? Show me the break-even.
```

### 📐 IaC Generator

```
Generate a Bicep template for a hub-spoke VNet with Azure Firewall and VPN Gateway.
```
```
Create Terraform modules for a multi-region AWS VPC with Transit Gateway.
```
```
Write an Ansible playbook to deploy NSGs and route tables for my Azure network.
```

### 🐳 Container Networking

```
Which CNI plugin should I use for my AKS cluster — Azure CNI Overlay or Cilium?
```
```
Design Kubernetes network policies to isolate namespaces while allowing shared services.
```
```
Compare Istio vs Linkerd for my service mesh — we need mTLS and traffic splitting.
```

### 🌐 CDN & Edge Networking

```
Design an Azure Front Door configuration with multi-origin failover and caching.
```
```
Optimize cache hit ratio for my API responses — what cache key strategy should I use?
```
```
Configure WAF rules at the edge to block bot traffic while allowing legitimate API calls.
```

### 🔄 Network Automation & GitOps

```
Design a GitHub Actions pipeline for deploying Terraform network changes with approval gates.
```
```
Set up drift detection to alert when someone makes out-of-band changes to my NSGs.
```
```
What policy-as-code rules should I enforce to prevent public IP creation in production?
```

### 🛡️ SASE / SSE

```
Design a SASE architecture to replace our legacy VPN for 5,000 remote users.
```
```
Compare Zscaler ZPA vs Microsoft Entra Private Access for our ZTNA implementation.
```
```
How should I integrate SD-WAN with our SASE platform for branch office connectivity?
```

### 📏 Network Capacity Planning

```
What VPN Gateway SKU do I need for 800 Mbps sustained throughput with 15 tunnels?
```
```
Forecast our ExpressRoute bandwidth needs — we're growing 30% per quarter.
```
```
Calculate maximum single-flow TCP throughput for a 50ms RTT link with 64KB window.
```

### 🔢 IPv6 Migration

```
Design a dual-stack VNet configuration for my Azure workloads.
```
```
Plan an IPv6 migration for our Azure environment — which services support IPv6 today?
```
```
Set up NAT64/DNS64 so my IPv6-only VMs can reach IPv4-only external services.
```

### 🔀 Multi-Domain (cross-specialist workflows)

```
Design a hub-spoke VNet, add firewall rules for east-west traffic, and set up monitoring.
```
```
Plan a hybrid connectivity setup with ExpressRoute, configure private endpoints for PaaS services, and audit the NSGs.
```
```
Troubleshoot connectivity from on-prem through VPN to a private endpoint, and check DNS resolution along the path.
```

### 🔎 Discovery

```
show me the cloud-networking capabilities
```
```
what tools does the firewall engineer have?
```
```
route this query: "I need to set up private endpoints for my storage accounts"
```

## Repository Structure

```
cloud-networking/
├── README.md                              # This file
├── LICENSE                                # MIT license
├── package.json                           # npm package config (name, bin, engines)
├── bin/
│   └── cli.mjs                            # CLI installer (init, uninstall, status)
└── extensions/
    └── cloud-networking/
        ├── extension.mjs                  # Router: cn_capabilities, cn_route, auto-routing hook
        └── specialists/
            ├── vnet-architect/
            │   ├── agents/
            │   │   └── vnet-architect.md
            │   └── skills/
            │       ├── address-planner/
            │       │   └── SKILL.md
            │       ├── hub-spoke-design/
            │       │   └── SKILL.md
            │       ├── migration-planner/
            │       │   └── SKILL.md
            │       ├── network-diagram/
            │       │   └── SKILL.md
            │       ├── peering-advisor/
            │       │   └── SKILL.md
            │       └── subnet-calculator/
            │           └── SKILL.md
            ├── firewall-engineer/
            │   ├── agents/
            │   │   └── firewall-engineer.md
            │   └── skills/
            │       ├── config-gen/
            │       │   └── SKILL.md
            │       ├── ha-design/
            │       │   └── SKILL.md
            │       ├── hardening-check/
            │       │   └── SKILL.md
            │       ├── log-analysis/
            │       │   └── SKILL.md
            │       ├── policy-design/
            │       │   └── SKILL.md
            │       ├── rule-audit/
            │       │   └── SKILL.md
            │       ├── troubleshoot/
            │       │   └── SKILL.md
            │       └── vendor-migrate/
            │           └── SKILL.md
            ├── load-balancer/
            │   ├── agents/
            │   │   └── load-balancer.md
            │   └── skills/
            │       ├── health-probe-design/
            │       │   └── SKILL.md
            │       ├── lb-selector/
            │       │   └── SKILL.md
            │       ├── ssl-offload/
            │       │   └── SKILL.md
            │       ├── traffic-routing/
            │       │   └── SKILL.md
            │       ├── troubleshoot/
            │       │   └── SKILL.md
            │       └── waf-rules/
            │           └── SKILL.md
            ├── dns-specialist/
            │   ├── agents/
            │   │   └── dns-specialist.md
            │   └── skills/
            │       ├── migration-plan/
            │       │   └── SKILL.md
            │       ├── record-audit/
            │       │   └── SKILL.md
            │       ├── resolver-design/
            │       │   └── SKILL.md
            │       ├── troubleshoot/
            │       │   └── SKILL.md
            │       └── zone-design/
            │           └── SKILL.md
            ├── private-link/
            │   ├── agents/
            │   │   └── private-link.md
            │   └── skills/
            │       ├── dns-integration/
            │       │   └── SKILL.md
            │       ├── endpoint-design/
            │       │   └── SKILL.md
            │       ├── security-review/
            │       │   └── SKILL.md
            │       ├── service-exposure/
            │       │   └── SKILL.md
            │       └── troubleshoot/
            │           └── SKILL.md
            ├── hybrid-connectivity/
            │   ├── agents/
            │   │   └── hybrid-connectivity.md
            │   └── skills/
            │       ├── bandwidth-calc/
            │       │   └── SKILL.md
            │       ├── expressroute-design/
            │       │   └── SKILL.md
            │       ├── failover-design/
            │       │   └── SKILL.md
            │       ├── routing-design/
            │       │   └── SKILL.md
            │       ├── troubleshoot/
            │       │   └── SKILL.md
            │       └── vpn-design/
            │           └── SKILL.md
            ├── network-security/
            │   ├── agents/
            │   │   └── network-security.md
            │   └── skills/
            │       ├── compliance-check/
            │       │   └── SKILL.md
            │       ├── ddos-design/
            │       │   └── SKILL.md
            │       ├── flow-analysis/
            │       │   └── SKILL.md
            │       ├── nsg-audit/
            │       │   └── SKILL.md
            │       ├── segmentation-design/
            │       │   └── SKILL.md
            │       └── troubleshoot/
            │           └── SKILL.md
            ├── network-troubleshooter/
            │   ├── agents/
            │   │   └── network-troubleshooter.md
            │   └── skills/
            │       ├── connectivity-test/
            │       │   └── SKILL.md
            │       ├── latency-analysis/
            │       │   └── SKILL.md
            │       ├── mtu-path-discovery/
            │       │   └── SKILL.md
            │       ├── nat-debug/
            │       │   └── SKILL.md
            │       ├── packet-capture/
            │       │   └── SKILL.md
            │       └── routing-debug/
            │           └── SKILL.md
            ├── vwan-sdwan/
            │   ├── agents/
            │   │   └── vwan-sdwan.md
            │   └── skills/
            │       ├── branch-connectivity/
            │       │   └── SKILL.md
            │       ├── nva-integration/
            │       │   └── SKILL.md
            │       ├── routing-intent/
            │       │   └── SKILL.md
            │       ├── troubleshoot/
            │       │   └── SKILL.md
            │       └── vwan-design/
            │           └── SKILL.md
            ├── network-monitor/
            │   ├── agents/
            │   │   └── network-monitor.md
            │   └── skills/
            │       ├── alert-design/
            │       │   └── SKILL.md
            │       ├── baseline-analysis/
            │       │   └── SKILL.md
            │       ├── connection-monitor/
            │       │   └── SKILL.md
            │       ├── dashboard-build/
            │       │   └── SKILL.md
            │       ├── flow-log-setup/
            │       │   └── SKILL.md
            │       └── traffic-analytics/
            │           └── SKILL.md
            └── multi-cloud-net/
                ├── agents/
                │   └── multi-cloud-net.md
                └── skills/
                    ├── addressing-plan/
                    │   └── SKILL.md
                    ├── cost-comparison/
                    │   └── SKILL.md
                    ├── latency-optimization/
                    │   └── SKILL.md
                    ├── service-mapping/
                    │   └── SKILL.md
                    └── transit-design/
                        └── SKILL.md
            ├── pricing-analyst/         # (structure follows same pattern)
            ├── iac-generator/
            │   ├── agents/
            │   │   └── iac-generator.md
            │   └── skills/
            │       ├── bicep-gen/
            │       │   └── SKILL.md
            │       ├── terraform-gen/
            │       │   └── SKILL.md
            │       ├── ansible-gen/
            │       │   └── SKILL.md
            │       └── arm-gen/
            │           └── SKILL.md
            ├── container-networking/
            │   ├── agents/
            │   │   └── container-networking.md
            │   └── skills/
            │       ├── cni-selection/
            │       │   └── SKILL.md
            │       ├── network-policy/
            │       │   └── SKILL.md
            │       ├── service-mesh/
            │       │   └── SKILL.md
            │       ├── ingress-design/
            │       │   └── SKILL.md
            │       ├── cross-cluster/
            │       │   └── SKILL.md
            │       └── troubleshoot/
            │           └── SKILL.md
            ├── cdn-edge/
            │   ├── agents/
            │   │   └── cdn-edge.md
            │   └── skills/
            │       ├── cdn-design/
            │       │   └── SKILL.md
            │       ├── edge-routing/
            │       │   └── SKILL.md
            │       ├── cache-optimization/
            │       │   └── SKILL.md
            │       ├── waf-edge/
            │       │   └── SKILL.md
            │       └── troubleshoot/
            │           └── SKILL.md
            ├── network-automation/
            │   ├── agents/
            │   │   └── network-automation.md
            │   └── skills/
            │       ├── pipeline-design/
            │       │   └── SKILL.md
            │       ├── drift-detection/
            │       │   └── SKILL.md
            │       ├── policy-as-code/
            │       │   └── SKILL.md
            │       ├── testing/
            │       │   └── SKILL.md
            │       └── rollback/
            │           └── SKILL.md
            ├── sase-sse/
            │   ├── agents/
            │   │   └── sase-sse.md
            │   └── skills/
            │       ├── architecture/
            │       │   └── SKILL.md
            │       ├── ztna-design/
            │       │   └── SKILL.md
            │       ├── swg-casb/
            │       │   └── SKILL.md
            │       ├── sdwan-integration/
            │       │   └── SKILL.md
            │       └── vendor-compare/
            │           └── SKILL.md
            ├── capacity-planner/
            │   ├── agents/
            │   │   └── capacity-planner.md
            │   └── skills/
            │       ├── bandwidth-forecast/
            │       │   └── SKILL.md
            │       ├── gateway-sizing/
            │       │   └── SKILL.md
            │       ├── throughput-calc/
            │       │   └── SKILL.md
            │       ├── scalability-design/
            │       │   └── SKILL.md
            │       └── growth-model/
            │           └── SKILL.md
            └── ipv6-migration/
                ├── agents/
                │   └── ipv6-migration.md
                └── skills/
                    ├── dual-stack/
                    │   └── SKILL.md
                    ├── transition-plan/
                    │   └── SKILL.md
                    ├── addressing/
                    │   └── SKILL.md
                    ├── compatibility/
                    │   └── SKILL.md
                    └── troubleshoot/
                        └── SKILL.md
```

### Installed extension structure

After running `cloud-networking init`, the installed layout mirrors the `extensions/cloud-networking/` tree above:

```
~/.copilot/extensions/cloud-networking/
├── extension.mjs                          # Router + auto-routing hook
└── specialists/                           # All 19 specialist directories
    └── (same structure as above)
```

### Specialist directory conventions

All specialists follow a standard layout:

```
specialist-name/
├── agents/
│   └── specialist-name.md    # Agent persona, workflow, guardrails
└── skills/
    ├── skill-name/
    │   └── SKILL.md          # Detailed skill instructions
    └── another-skill/
        └── SKILL.md
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Extensions not loading (`/env` shows "Extensions: none") | Enable experimental mode: `copilot --experimental` — or use project-level install: `cloud-networking init --project` |
| Tools not appearing after install | Restart Copilot CLI to reload extensions |
| `cn_capabilities` not found | Verify `~/.copilot/extensions/cloud-networking/extension.mjs` exists |
| Specialist tools missing | Run `cloud-networking status` to check — should list all 19 specialists |
| Conflicting individual extensions | Run `cloud-networking init` — it removes old standalone specialist installs |
| `npx` hangs or fails | Use Option E (manual install) — clone the repo and copy files directly |
| Firewall config for unsupported vendor | Check the [14 supported vendors](#firewall-vendors-14) list |
| Version mismatch after update | Run `cloud-networking status` — compare CLI version vs installed version |

## License

MIT
