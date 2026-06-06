# Network Desk

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js >= 18](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org/)

**Your cloud networking AI team for GitHub Copilot CLI.** 20 specialist agents covering VNet design, firewalls (14 vendors), load balancing, DNS, private connectivity, IaC generation, container networking, CDN/edge, SASE/SSE, and more — routed automatically.

---

### 📌 Table of Contents

| | Section | Description |
|---|---------|-------------|
| 🚀 | [Quick Start](#quick-start) | One-command install |
| 💡 | [What is Network Desk?](#what-is-network-desk) | Overview and key concepts |
| 👥 | [The Team](#the-team) | All 20 specialists at a glance |
| 📦 | [Installation](#installation) | 5 ways to install (npx user-level, npx project-level, npm, Copilot prompt, manual) |
| 🖥️ | [CLI Reference](#cli-reference) | `init`, `status`, `uninstall`, `--version` |
| ⚙️ | [How It Works](#how-it-works) | Architecture, routing, and workflow |
| 📚 | [Validation-first: per-cloud documentation MCP](#validation-first-per-cloud-documentation-mcp) | Authoritative validation of Azure/AWS/GCP facts |
| 📝 | [Usage Examples](#usage-examples) | Example prompts for every specialist |
| 📁 | [Output files](#output-files) | Where generated diagrams, reports, and configs are saved |
| 📂 | [Repository Structure](#repository-structure) | Full folder tree and conventions |
| 🔧 | [Troubleshooting](#troubleshooting) | Common issues and fixes |
| 🔒 | [Privacy](#privacy) | How the extension handles your data |
| 📜 | [Changelog](CHANGELOG.md) | Release notes and version history |
| 📄 | [License](#license) | MIT |

---

## Quick Start

```bash
npx github:dmauser/network-desk init
```

That's it. Launch Copilot CLI with experimental mode (`copilot --experimental`) in any repo and trigger the extension with **`@network-desk`** followed by what you need:

```
@network-desk design a hub-spoke VNet topology for a 3-tier app across dev/staging/prod
```

```
@network-desk generate Palo Alto rules to allow HTTPS from my app subnet to a backend on port 8443
```

The coordinator picks the right specialist automatically and responds in plain language — no tool names to remember.

## What is Network Desk?

Network Desk gives you a coordinated team of network specialist agents through [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/about-copilot-cli). Describe what you need — VNet design, firewall rules, DNS troubleshooting, hybrid connectivity, IaC generation, container networking, SASE architecture — and the coordinator routes your request to the right specialist automatically.

Each specialist operates within a defined area of domain expertise, supported by tailored guardrails and structured workflows. The coordinator is responsible for routing requests and orchestrating cross-domain interactions, eliminating the need for users to manage or select individual tools.

> **Analysis only** — Network Desk produces designs, configurations, IaC templates, and analysis for human review. It generates deployment code but does not execute deployments, modify live firewalls, or make changes to production networks.

## The Team

| | Specialist | `specialist` | What They Do |
|---|-----------|--------|-------------|
| 🏗️ | **VNet/Subnet Architect** | `cn_vnet` | VNet/VPC design, hub-spoke, peering, address planning, ASCII/Mermaid/Excalidraw/draw.io diagrams |
| 🔥 | **Firewall Engineer** | `cn_fw` | Multi-vendor firewall rules, policies, migration, config gen (14 vendors) |
| ⚖️ | **Load Balancer** | `cn_lb` | LB selection, health probes, SSL offload, WAF, traffic routing |
| 🌐 | **DNS Specialist** | `cn_dns` | DNS zones, resolvers, record audits, migration, troubleshooting |
| 🔒 | **Private Link Engineer** | `cn_pl` | Private endpoints, DNS integration, service exposure, security |
| 🔗 | **Hybrid Connectivity** | `cn_hyb` | VPN, ExpressRoute, Direct Connect, BGP, failover design |
| 🛡️ | **Network Security** | `cn_nsec` | NSG audits, segmentation, DDoS, flow analysis, compliance |
| 🔧 | **Network Troubleshooter** | `cn_ntsh` | Connectivity tests, packet capture, latency, routing, NAT, MTU |
| 🌍 | **Virtual WAN / SD-WAN** | `cn_vwan` | vWAN design, routing intent, NVA integration, branch connectivity |
| 📊 | **Network Monitor** | `cn_nmon` | Flow logs, traffic analytics, connection monitors, dashboards, alerts |
| ☁️ | **Multi-Cloud Networking** | `cn_mcn` | Cross-cloud transit, addressing, service mapping, cost comparison |
| 💰 | **Pricing Analyst** | `cn_price` | Network cost estimation, egress calculation, pricing comparison, cost optimization |
| 📐 | **IaC Generator** | `cn_iac` | Bicep, Terraform, Ansible, ARM templates for networking infrastructure |
| 🐳 | **Container Networking** | `cn_cnet` | CNI plugins, network policies, service mesh, ingress, multi-cluster (AKS/EKS/GKE) |
| 🌐 | **CDN & Edge Networking** | `cn_cdn` | Azure Front Door, CloudFront, Cloud CDN, edge routing, caching, WAF at edge |
| 🔄 | **Network Automation & GitOps** | `cn_nauto` | CI/CD pipelines, drift detection, policy-as-code, testing, rollback |
| 🛡️ | **SASE / SSE** | `cn_sase` | ZTNA, SWG, CASB, FWaaS, SD-WAN integration, vendor comparison |
| 📏 | **Network Capacity Planning** | `cn_ncap` | Bandwidth forecasting, gateway sizing, throughput calculations, growth modeling |
| 🔢 | **IPv6 Migration** | `cn_ipv6` | Dual-stack design, transition planning, addressing, NAT64/DNS64, troubleshooting |
| 📄 | **Report Builder** | `cn_doc` | Packages findings into polished Markdown/HTML/PDF/DOCX reports and XLSX models with formulas |

> The `specialist` column is the value the coordinator passes internally (e.g. `cn_role({ specialist: "cn_vnet" })`). The bare forms (`vnet`, `fw`, …) are still accepted as aliases. You never type these — just describe what you need after `@network-desk`.

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
npx github:dmauser/network-desk init
```

Then launch Copilot with experimental mode:

```bash
copilot --experimental
```

This will:
1. Create `~/.copilot/extensions/network-desk/` if it doesn't exist
2. Copy the extension router and all 20 specialists
3. Remove any conflicting individual specialist extensions
4. Display a summary of what was installed

### Option B — Project-level install (no experimental mode needed)

Installs the extension into the current repo's `.github/extensions/` directory. Works without experimental mode, but only for this repo.

> **Important:** You must run this from inside a git repository. If you don't have one yet, run `git init` first.

```bash
# cd into your repo first
cd my-repo
npx github:dmauser/network-desk init --project
```

Then launch Copilot normally from the repo:

```bash
copilot
```

This will:
1. Create `.github/extensions/network-desk/` in the current repo
2. Copy the extension router and all 20 specialists
3. Add the extension directory to `.gitignore` (each developer runs init themselves)

### Option C — Global install via npm

If you prefer a persistent CLI command instead of `npx`:

```bash
npm install -g github:dmauser/network-desk

# User-level install (requires experimental mode)
network-desk init

# Or project-level install (no experimental mode needed)
network-desk init --project

# Now available as a command:
network-desk status
network-desk --version
```

### Option D — Install from inside Copilot CLI

Already have Copilot CLI open? You can install directly from the prompt — just ask Copilot to clone the repo and run the installer for you:

```
Clone https://github.com/dmauser/network-desk.git and run `node bin/cli.mjs init` from the cloned directory.
```

Or if you already cloned the repo and are inside it:

```
Run `node bin/cli.mjs init` to install the network-desk extensions.
```

Copilot will execute the commands, copy the extensions into `~/.copilot/extensions/network-desk/`, and confirm the result. After installation, restart Copilot CLI to load the new extensions, then verify with:

```
show me the network-desk capabilities
```

### Option E — Manual install (offline / corporate environments)

<details>
<summary>Click to expand manual steps</summary>

Use this if you're behind a corporate proxy or don't have access to npm/npx.

**Step 1 — Clone the repo:**

```bash
git clone https://github.com/dmauser/network-desk.git
cd network-desk
```

**Step 2 — Copy to your Copilot extensions directory:**

macOS / Linux:

```bash
mkdir -p ~/.copilot/extensions/network-desk
cp -r extensions/network-desk/* ~/.copilot/extensions/network-desk/
```

Windows (PowerShell):

```powershell
$dest = "$env:USERPROFILE\.copilot\extensions\network-desk"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path "extensions\network-desk\*" -Destination $dest -Recurse -Force
```

**Step 3 — Verify the files are in place:**

```bash
ls ~/.copilot/extensions/network-desk/
# Should show: extension.mjs  specialists/
```

</details>

### Option F — Install as a native Copilot CLI plugin

Network Desk can also be installed as a **native Copilot CLI plugin** (the `copilot plugin` system) instead of an SDK extension. The plugin ships **one coordinator agent** (`Network Desk`) that routes to **20 specialist skills** — generated from the same single source of truth as the extension, so you get the same specialist depth.

**Easiest — via the CLI helper** (registers a local marketplace, then installs):

```bash
npx github:dmauser/network-desk init --plugin
# or, if installed globally:
network-desk init --plugin
```

**Manually with the `copilot` CLI:**

```bash
# Register the repo as a marketplace, then install by name (recommended)
copilot plugin marketplace add dmauser/network-desk
copilot plugin install network-desk@network-desk

# Verify
copilot plugin list
```

Remove it with `network-desk uninstall --plugin` (or `copilot plugin uninstall network-desk`).

**Extension vs. plugin — which should I use?**

| | Extension (`init`) | Plugin (`init --plugin`) |
|---|---|---|
| Install target | `~/.copilot/extensions/` or `.github/extensions/` | `copilot plugin` store |
| Routing | Deterministic regex hooks + `cn_*` tools | LLM-driven via the coordinator agent |
| Experimental mode | Required for user-level | Not required |
| Specialist depth | Full | Full (deep docs bundled as skill `reference/`) |

Both are generated from the same registry. The plugin bundle lives in [`plugins/network-desk/`](plugins/network-desk/); regenerate it after registry changes with `network-desk plugin build`.

### Verify installation

After any install method, check that everything is in place:

```bash
# If you used Option A or B:
npx github:dmauser/network-desk status

# Or launch Copilot CLI and ask:
copilot
> show me the network-desk capabilities
```

You should see all 20 specialists listed with their tools.

### Updating

The extension automatically checks GitHub for a newer version on each session start (throttled to once every 24h, fully non-blocking, never blocks load). When an update is available, you'll see a one-line `network-desk: update available — installed X.Y.Z, latest A.B.C` notice in the session log.

To update, run the **`update`** command — it auto-detects whether you have a user-level install, a project-level install (in the current repo), or both, and re-installs each in place:

```bash
npx github:dmauser/network-desk update
```

Equivalent shortcuts (any of these re-pulls the latest):

```bash
# Re-run init explicitly (replaces the existing install)
npx github:dmauser/network-desk init             # user-level
npx github:dmauser/network-desk init --project   # project-level

# If installed globally
npm install -g github:dmauser/network-desk
network-desk update
```

**Opt out of auto-check.** Set the environment variable `NETWORK_DESK_NO_UPDATE_CHECK=1` to disable the periodic GitHub poll entirely.

Each install records its version in `<install-dir>/.install-meta.json`, and `network-desk status` will display it alongside the install date.

See [CHANGELOG.md](CHANGELOG.md) for what's new in each release.

### Uninstall

```bash
# Using the CLI:
npx github:dmauser/network-desk uninstall

# Or manually:
# macOS / Linux
rm -rf ~/.copilot/extensions/network-desk
# Windows (PowerShell)
Remove-Item -Recurse -Force "$env:USERPROFILE\.copilot\extensions\network-desk"
```

## CLI Reference

The `network-desk` CLI manages installation of the Copilot extensions. You can run it via `npx` or install it globally.

| Command | Description |
|---------|-------------|
| `network-desk init` | Install/reinstall extensions to `~/.copilot/extensions/` |
| `network-desk init --project` | Install extensions to `.github/extensions/` in current repo |
| `network-desk init --plugin` | Install as a native Copilot CLI plugin (registers a local marketplace, then installs) |
| `network-desk plugin build` | (Re)generate the plugin bundle in `plugins/network-desk/` from the registry source |
| `network-desk update` | Re-install over any existing user-level and/or project-level install (pulls latest from GitHub) |
| `network-desk status` | Check installation status, version, and list available specialists |
| `network-desk uninstall` | Remove installed extensions |
| `network-desk uninstall --plugin` | Remove the installed Copilot CLI plugin |
| `network-desk --version` | Print the installed CLI version |
| `network-desk help` | Show CLI help |

The extension also performs an **automatic update check** against GitHub once every 24 hours when a Copilot session starts, and prints a one-line notice if a newer version is available. Set `NETWORK_DESK_NO_UPDATE_CHECK=1` to disable. This is the extension's only outbound network request — see [Privacy](#privacy) / [PRIVACY.md](PRIVACY.md).

## How It Works

Trigger the extension with **`@network-desk`** anywhere in your prompt — or just ask a networking question. The coordinator announces itself at session start, auto-detects networking intent (even without the `@` mention), picks the right specialist(s), loads their role and skills behind the scenes via the registered tools, and replies in natural language. Each routing hint is shown once per specialist per session to keep the conversation clean.

```
You: @network-desk design a hub-spoke VNet with Azure Firewall and
     monitor east-west traffic with flow logs

         │
         ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ Network Desk coordinator                                    │
   │ • Detects @network-desk mention                             │
   │ • Identifies multi-domain intent:                           │
   │     VNet design · Firewall · Network monitoring             │
   │ • Engages the matching specialists in sequence              │
   └─────────────────────────────────────────────────────────────┘
         │
         ▼
   Specialists run their domain workflows and the coordinator
   stitches the answer together in plain language.
```

You never need to call individual tools — just describe what you need after `@network-desk` and the coordinator handles the rest.

## Validation-first: per-cloud documentation MCP

Network Desk treats an **official documentation MCP server** as its **primary source of truth for each cloud**. When the relevant server is configured, specialists validate every networking fact — service SKUs/tiers, limits & quotas, regional availability, feature support, pricing dimensions, and API/CLI/IaC syntax & versions — against current docs **before** stating it, treat the docs MCP as authoritative (if it contradicts built-in knowledge, **the docs MCP wins**), and cite the exact doc URL(s).

| Cloud | Server | Tools | Transport |
|-------|--------|-------|-----------|
| **Azure** | [Microsoft Learn MCP](https://github.com/MicrosoftDocs/mcp) | `microsoft_docs_search`, `microsoft_docs_fetch`, `microsoft_code_sample_search` | hosted HTTP (no account/API key) |
| **AWS** | [AWS Documentation MCP](https://github.com/awslabs/mcp/tree/main/src/aws-documentation-mcp-server) | `search_documentation`, `read_documentation`, `recommend` | local stdio (`uvx`) |
| **GCP** | *Configurable* `gcp-docs` placeholder | your chosen GCP docs MCP tools | local stdio |

Add the servers with `copilot mcp add` (or run `/mcp` inside a Copilot CLI session and follow the wizard):

```bash
# Azure — Microsoft Learn (hosted HTTP)
copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp

# AWS — AWS Documentation MCP (local stdio; requires uv/uvx + Python ≥3.10 — https://docs.astral.sh/uv/)
copilot mcp add aws-docs --env FASTMCP_LOG_LEVEL=ERROR --env AWS_DOCUMENTATION_PARTITION=aws -- uvx awslabs.aws-documentation-mcp-server@latest

# GCP — placeholder: substitute your chosen GCP docs MCP server command
copilot mcp add gcp-docs -- <your-gcp-docs-mcp-command>
```

If a cloud's docs MCP is **not** configured, Network Desk still works, but that cloud's answers run in a clearly-labelled **unverified** mode: the response is prepended with a ⚠️ warning banner, numeric specs and limits are marked *indicative, unverified*, and the matching setup command above is included. This guarantees you can always tell whether an answer was docs-MCP-validated (with URLs) or produced from built-in knowledge alone.

**Scope:** Each docs MCP covers its own cloud only. For the **14 firewall vendors**, there is no docs MCP — Network Desk validates against the official vendor documentation and keeps its standard *"Analysis only — verify against vendor documentation before applying."* guardrail.

This is a **per-user** Copilot CLI setting — it is configured at the CLI level, not by this extension. It is shared across all your sessions and repos, and uninstalling Network Desk does not change it. Network Desk never edits your MCP configuration; you add or remove the server yourself.

## Usage Examples

Trigger the extension with **`@network-desk`** and describe what you need in plain language — the coordinator picks the right specialist automatically.

### 🏗️ VNet/Subnet Architect

```
@network-desk Design a hub-spoke VNet topology for a 3-tier app with separate dev/staging/prod environments.
```
```
@network-desk Plan an IP address scheme for 12 VNets across 3 Azure regions with no overlapping CIDRs.
```
```
@network-desk Generate a Mermaid diagram of my current hub-spoke peering architecture.
```

### 🔥 Firewall Engineer

```
@network-desk Generate Palo Alto PAN-OS rules to allow HTTPS from my app subnet to a backend API on port 8443.
```
```
@network-desk Migrate these Cisco ASA ACLs to Azure Firewall policy rules.
```
```
@network-desk Audit my FortiGate ruleset for shadowed, redundant, or overly permissive rules.
```

### ⚖️ Load Balancer

```
@network-desk Which Azure load balancer should I use — Standard LB, App Gateway, or Front Door?
```
```
@network-desk Design health probes for a multi-region API behind Azure Front Door.
```
```
@network-desk Configure SSL offload on an Application Gateway with end-to-end TLS.
```

### 🌐 DNS Specialist

```
@network-desk Design a private DNS zone architecture for 5 VNets with hub-spoke peering.
```
```
@network-desk Audit my DNS records for stale entries, mismatched TTLs, and missing PTR records.
```
```
@network-desk Troubleshoot — internal VMs can't resolve privatelink.blob.core.windows.net.
```

### 🔒 Private Link Engineer

```
@network-desk Set up private endpoints for Azure SQL and Storage with proper DNS integration.
```
```
@network-desk Review the security posture of my private endpoint configuration — any gaps?
```
```
@network-desk Expose my internal API to a partner tenant using Private Link Service.
```

### 🔗 Hybrid Connectivity

```
@network-desk Design a site-to-site VPN between Azure and our on-prem data center with BGP.
```
```
@network-desk Plan an ExpressRoute circuit with Global Reach for US-East and West Europe.
```
```
@network-desk Design a failover strategy: ExpressRoute primary, VPN backup with automatic failover.
```

### 🛡️ Network Security

```
@network-desk Audit all NSGs in my subscription — flag any-any rules, unused NSGs, and overly broad ranges.
```
```
@network-desk Design a micro-segmentation strategy for a PCI-DSS compliant environment.
```
```
@network-desk Analyze NSG flow logs to identify top talkers and unexpected traffic patterns.
```

### 🔧 Network Troubleshooter

```
@network-desk My VM in spoke-vnet-02 can't reach the database in hub-vnet — diagnose the connectivity path.
```
```
@network-desk Run a packet capture on my NVA to debug why return traffic is being dropped.
```
```
@network-desk Investigate high latency between my Azure VMs and on-prem servers — is it routing or MTU?
```

### 🌍 Virtual WAN / SD-WAN

```
@network-desk Design a Virtual WAN topology for 20 branch offices across 3 regions.
```
```
@network-desk Configure routing intent for internet breakout through Azure Firewall in my vWAN hub.
```
```
@network-desk Integrate a Palo Alto NVA into my Virtual WAN hub for traffic inspection.
```

### 📊 Network Monitor

```
@network-desk Set up NSG flow logs with Traffic Analytics for all my production VNets.
```
```
@network-desk Build a monitoring dashboard for VPN gateway throughput, latency, and tunnel status.
```
```
@network-desk Create alert rules for when ExpressRoute circuit utilization exceeds 80%.
```

### ☁️ Multi-Cloud Networking

```
@network-desk Design a transit architecture connecting Azure, AWS, and GCP with consistent addressing.
```
```
@network-desk Map equivalent networking services across Azure, AWS, and GCP for our migration plan.
```
```
@network-desk Compare the cost of cross-cloud connectivity options: VPN vs dedicated interconnect vs SD-WAN.
```

### 💰 Pricing Analyst

```
@network-desk How much will 5TB of monthly egress from Azure East US cost?
```
```
@network-desk Compare VPN gateway costs across Azure, AWS, and GCP for 500 Mbps.
```
```
@network-desk Should I use ExpressRoute or S2S VPN for 2 Gbps sustained? Show me the break-even.
```

### 📐 IaC Generator

```
@network-desk Generate a Bicep template for a hub-spoke VNet with Azure Firewall and VPN Gateway.
```
```
@network-desk Create Terraform modules for a multi-region AWS VPC with Transit Gateway.
```
```
@network-desk Write an Ansible playbook to deploy NSGs and route tables for my Azure network.
```

### 🐳 Container Networking

```
@network-desk Which CNI plugin should I use for my AKS cluster — Azure CNI Overlay or Cilium?
```
```
@network-desk Design Kubernetes network policies to isolate namespaces while allowing shared services.
```
```
@network-desk Compare Istio vs Linkerd for my service mesh — we need mTLS and traffic splitting.
```

### 🌐 CDN & Edge Networking

```
@network-desk Design an Azure Front Door configuration with multi-origin failover and caching.
```
```
@network-desk Optimize cache hit ratio for my API responses — what cache key strategy should I use?
```
```
@network-desk Configure WAF rules at the edge to block bot traffic while allowing legitimate API calls.
```

### 🔄 Network Automation & GitOps

```
@network-desk Design a GitHub Actions pipeline for deploying Terraform network changes with approval gates.
```
```
@network-desk Set up drift detection to alert when someone makes out-of-band changes to my NSGs.
```
```
@network-desk What policy-as-code rules should I enforce to prevent public IP creation in production?
```

### 🛡️ SASE / SSE

```
@network-desk Design a SASE architecture to replace our legacy VPN for 5,000 remote users.
```
```
@network-desk Compare Zscaler ZPA vs Microsoft Entra Private Access for our ZTNA implementation.
```
```
@network-desk How should I integrate SD-WAN with our SASE platform for branch office connectivity?
```

### 📏 Network Capacity Planning

```
@network-desk What VPN Gateway SKU do I need for 800 Mbps sustained throughput with 15 tunnels?
```
```
@network-desk Forecast our ExpressRoute bandwidth needs — we're growing 30% per quarter.
```
```
@network-desk Calculate maximum single-flow TCP throughput for a 50ms RTT link with 64KB window.
```

### 🔢 IPv6 Migration

```
@network-desk Design a dual-stack VNet configuration for my Azure workloads.
```
```
@network-desk Plan an IPv6 migration for our Azure environment — which services support IPv6 today?
```
```
@network-desk Set up NAT64/DNS64 so my IPv6-only VMs can reach IPv4-only external services.
```

### 📄 Report Builder

```
@network-desk Package the firewall rule-audit findings into a polished PDF report.
```
```
@network-desk Export this hub-spoke design review as a Word document with an executive summary.
```
```
@network-desk Build an XLSX capacity model with formulas for subnet sizing and growth.
```

> Report Builder is a **packaging** specialist — it turns another specialist's analysis into a deliverable. It does not perform networking analysis itself. Generated files land under `network-desk/<specialist>/reports/` (see [Output files](#output-files)). Rendering to PDF/DOCX/XLSX uses the bundled Python renderers (`renderers/make_*.py`); when a dependency is missing the skill falls back to Markdown/HTML.

### 🔀 Multi-Domain (cross-specialist workflows)

```
@network-desk Design a hub-spoke VNet, add firewall rules for east-west traffic, and set up monitoring.
```
```
@network-desk Plan a hybrid connectivity setup with ExpressRoute, configure private endpoints for PaaS services, and audit the NSGs.
```
```
@network-desk Troubleshoot connectivity from on-prem through VPN to a private endpoint, and check DNS resolution along the path.
```

### 🔎 Discovery

```
@network-desk what can you help me with?
```
```
@network-desk which specialists cover firewalls and what do they do?
```
```
@network-desk I need to set up private endpoints for my storage accounts — who should handle this?
```

## Output files

Specialists are **analysis-first** and return their findings inline in the chat. When you ask for a saved artifact — a diagram, a rendered report, or a spreadsheet model — files are written into a predictable tree rooted at `network-desk/` in your current working directory:

```
network-desk/
└── <specialist>/            # kebab dir name, e.g. firewall-engineer, capacity-planner
    ├── diagrams/            # ASCII (.txt) / Mermaid / Excalidraw / draw.io sources
    ├── reports/             # Markdown / HTML / PDF / DOCX deliverables
    └── configs/             # generated configs / IaC / specs
```

Files are named `<kebab-topic>-<YYYYMMDD>.<ext>` by default (e.g. `rule-audit-20260115.pdf`). Example:

```
network-desk/
├── firewall-engineer/
│   ├── reports/rule-audit-20260115.pdf
│   └── configs/east-west-policy-20260115.json
└── capacity-planner/
    └── reports/ip-plan-20260115.xlsx
```

The bundled Python renderers (`extensions/network-desk/renderers/make_{html,pdf,docx,xlsx}.py`) honor this layout: pass `--specialist <kebab-dir>` and they resolve the output path automatically (override with `--output`/`--outdir`). The [Report Builder](#-report-builder) specialist orchestrates these renderers for high-quality reports.

## Repository Structure

```
network-desk/
├── README.md                              # This file
├── LICENSE                                # MIT license
├── package.json                           # npm package config (name, bin, engines)
├── bin/
│   └── cli.mjs                            # CLI installer (init, uninstall, status)
└── extensions/
    └── network-desk/
        ├── extension.mjs                  # Router: @network-desk mention trigger + auto-routing hook
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
            ├── ipv6-migration/
                │   ├── agents/
                │   │   └── ipv6-migration.md
                │   └── skills/
                │       ├── dual-stack/
                │       │   └── SKILL.md
                │       ├── transition-plan/
                │       │   └── SKILL.md
                │       ├── addressing/
                │       │   └── SKILL.md
                │       ├── compatibility/
                │       │   └── SKILL.md
                │       └── troubleshoot/
                │           └── SKILL.md
                └── report-builder/
                    ├── agents/
                    │   └── report-builder.md
                    └── skills/
                        ├── report-structure/
                        │   └── SKILL.md
                        ├── html-report/
                        │   └── SKILL.md
                        ├── pdf-report/
                        │   └── SKILL.md
                        ├── docx-report/
                        │   └── SKILL.md
                        └── xlsx-workbook/
                            └── SKILL.md
```

### Installed extension structure

After running `network-desk init`, the installed layout mirrors the `extensions/network-desk/` tree above:

```
~/.copilot/extensions/network-desk/
├── extension.mjs                          # Router + auto-routing hook
└── specialists/                           # All 20 specialist directories
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
| Extensions not loading (`/env` shows "Extensions: none") | Enable experimental mode: `copilot --experimental` — or use project-level install: `network-desk init --project` |
| Tools not appearing after install | Restart Copilot CLI to reload extensions |
| `@network-desk` doesn't engage | Verify `~/.copilot/extensions/network-desk/extension.mjs` exists; run `network-desk status` |
| Specialist tools missing | Run `network-desk status` to check — should list all 20 specialists |
| Conflicting individual extensions | Run `network-desk init` — it removes old standalone specialist installs |
| `npx` hangs or fails | Use Option E (manual install) — clone the repo and copy files directly |
| Firewall config for unsupported vendor | Check the [14 supported vendors](#firewall-vendors-14) list |
| Version mismatch after update | Run `network-desk status` — compare CLI version vs installed version |

## Privacy

Network Desk is a **local, read-only** extension. It collects **no telemetry** and never
transmits your prompts, code, or generated files. Its only outbound request is an optional
once-per-24-hours version check against GitHub, which you can disable with
`NETWORK_DESK_NO_UPDATE_CHECK=1`.

See [PRIVACY.md](PRIVACY.md) for full details on what data is accessed, what leaves your
machine, the local files written, and your controls.

## License

MIT — see [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a full list of releases, new specialists, skill additions, and behavior changes.

