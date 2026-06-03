# Network Desk — Copilot CLI Plugin

Your cloud networking AI team, packaged as a **native GitHub Copilot CLI plugin**. One coordinator agent (`Network Desk`) routes your request to one of 20 specialist skills across Azure, AWS, GCP and 14 firewall vendor platforms.

> Generated from the Network Desk single source of truth. Do not edit by hand —
> run `node extensions/network-desk/scripts/build-plugin.mjs` to regenerate.

## Install

Directly from the repository (no marketplace needed):

```sh
copilot plugin install dmauser/network-desk:plugins/network-desk
```

Or register the repo as a marketplace, then install by name:

```sh
copilot plugin marketplace add dmauser/network-desk
copilot plugin install network-desk@network-desk
```

## Specialists

| Specialist | Skill | Domain |
| --- | --- | --- |
| 🏗️ VNet/Subnet Architect | `network-desk-vnet` | VNet/Subnet Architecture |
| 🔥 Firewall Engineer | `network-desk-fw` | Firewall Engineering |
| ⚖️ Load Balancer | `network-desk-lb` | Load Balancing |
| 🌐 DNS Specialist | `network-desk-dns` | DNS |
| 🔒 Private Link Engineer | `network-desk-pl` | Private Link / Endpoints |
| 🔗 Hybrid Connectivity | `network-desk-hyb` | Hybrid Connectivity |
| 🛡️ Network Security | `network-desk-nsec` | Network Security |
| 🔧 Network Troubleshooter | `network-desk-ntsh` | Network Troubleshooting |
| 🌍 Virtual WAN / SD-WAN | `network-desk-vwan` | Virtual WAN / SD-WAN |
| 📊 Network Monitor | `network-desk-nmon` | Network Monitoring |
| ☁️ Multi-Cloud Networking | `network-desk-mcn` | Multi-Cloud Networking |
| 💰 Pricing Analyst | `network-desk-price` | Network Pricing |
| 📐 IaC Generator | `network-desk-iac` | IaC Generator |
| 🐳 Container Networking | `network-desk-cnet` | Container Networking |
| 🌐 CDN & Edge Networking | `network-desk-cdn` | CDN & Edge Networking |
| 🔄 Network Automation & GitOps | `network-desk-nauto` | Network Automation & GitOps |
| 🛡️ SASE / SSE | `network-desk-sase` | SASE / SSE |
| 📏 Network Capacity Planning | `network-desk-ncap` | Network Capacity Planning |
| 🔢 IPv6 Migration | `network-desk-ipv6` | IPv6 Migration |
| 📄 Report Builder | `network-desk-doc` | Documentation & Reporting |

## Extension vs. plugin

This plugin is an **alternative** to the Network Desk SDK extension. The extension form (installed via `network-desk init`) keeps deterministic regex-based routing and the parameterized `cn_*` tools. The plugin form uses **LLM-driven routing** through the coordinator agent — simpler to install, slightly less deterministic. Both are generated from the same source and deliver the same specialist depth.

---

*Analysis only — verify against vendor documentation before applying.*
