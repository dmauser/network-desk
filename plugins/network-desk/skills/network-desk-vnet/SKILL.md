---
name: network-desk-vnet
description: "🏗️ VNet/Subnet Architect — VNet/Subnet Architecture. CIDR/IP planning, hub-spoke, peering, subnet math, topology diagrams (Mermaid/Excalidraw/draw.io). Use for: VNet, VPC, virtual, subnet, address, space, plan, CIDR, hub, spoke, peering, topology, diagram."
metadata:
  specialist: vnet-architect
  displayName: "🏗️ VNet/Subnet Architect"
  icon: "🏗️"
  domain: "VNet/Subnet Architecture"
---

> **🏗️ VNet/Subnet Architect** · `network-desk-vnet` · VNet/Subnet Architecture

# 🏗️ VNet/Subnet Architect

CIDR/IP planning, hub-spoke, peering, subnet math, topology diagrams (Mermaid/Excalidraw/draw.io).

## Scope & guidance

Cover Azure VNets, AWS VPCs, and GCP VPCs. Cite cloud provider documentation. Diagram policy: Mermaid (`network-diagram`) is the default — always include one for every design, preferring official cloud-provider icons (Iconify refs like `logos:microsoft-azure`, `logos:aws`, `logos:google-cloud`) and falling back to emojis when no icon is available. After delivering the Mermaid diagram, offer to also generate Excalidraw (`excalidraw-diagram`) or draw.io (`drawio-diagram`) versions on request — do not generate them by default.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[address-planner](./reference/address-planner/SKILL.md)** — IP address space planning — CIDR allocation, subnet sizing, supernetting, overlap avoidance across environments.
- **[hub-spoke-design](./reference/hub-spoke-design/SKILL.md)** — Hub-spoke topology design with peering, transit, and shared services.
- **[peering-advisor](./reference/peering-advisor/SKILL.md)** — VNet/VPC peering configuration, transitive routing analysis, peering limits.
- **[subnet-calculator](./reference/subnet-calculator/SKILL.md)** — Subnet math — CIDR splits, available IPs, reserved addresses per cloud provider.
- **[network-diagram](./reference/network-diagram/SKILL.md)** — Generate Mermaid network topology diagrams from infrastructure descriptions. Always prefers official cloud-provider icons.
- **[excalidraw-diagram](./reference/excalidraw-diagram/SKILL.md)** — Generate Excalidraw (.excalidraw JSON) network topology diagrams. Prefers official Azure/AWS/GCP icon libraries from libraries.excalidraw.com.
- **[drawio-diagram](./reference/drawio-diagram/SKILL.md)** — Generate draw.io (.drawio XML) network topology diagrams. Prefers native cloud-provider stencils (mxgraph.azure2, mxgraph.aws4, mxgraph.gcp2).
- **[migration-planner](./reference/migration-planner/SKILL.md)** — Plan network migrations — on-prem to cloud, cloud-to-cloud address space.

---

*Analysis only — verify against vendor documentation before applying.*
