---
name: network-desk-mcn
description: "☁️ Multi-Cloud Networking — Multi-Cloud Networking. Transit design, cross-cloud addressing, service mapping, latency/cost comparison. Use for: multi, cloud, connect, transit, cross, architecture, interconnect, service, mapping, across, between."
metadata:
  specialist: multi-cloud-net
  displayName: "☁️ Multi-Cloud Networking"
  icon: "☁️"
  domain: "Multi-Cloud Networking"
---

> **☁️ Multi-Cloud Networking** · `network-desk-mcn` · Multi-Cloud Networking

# ☁️ Multi-Cloud Networking

Transit design, cross-cloud addressing, service mapping, latency/cost comparison.

## Scope & guidance

Covers cross-cloud connectivity architectures, service equivalency mapping, and cost analysis.

## Validation policy (Microsoft Learn MCP — Azure source of truth)

Validation-first: validate every Azure fact against the Microsoft Learn MCP server before stating it (Learn wins on conflict; cite the Learn URL). If no Learn MCP server is configured, label Azure answers ⚠️ unverified and suggest `copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`. AWS/GCP/firewall facts: verify against official vendor docs.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[transit-design](./reference/transit-design/SKILL.md)** — Multi-cloud transit architecture — VPN mesh, cloud-native interconnects, NVA transit.
- **[addressing-plan](./reference/addressing-plan/SKILL.md)** — Cross-cloud IP address plan — non-overlapping CIDR, summarization, NAT strategies.
- **[service-mapping](./reference/service-mapping/SKILL.md)** — Map networking services across clouds (Azure VNet ↔ AWS VPC ↔ GCP VPC).
- **[latency-optimization](./reference/latency-optimization/SKILL.md)** — Cross-cloud latency optimization — peering locations, backbone routing, CDN.
- **[cost-comparison](./reference/cost-comparison/SKILL.md)** — Network cost comparison across clouds — egress, peering, VPN, interconnect pricing.

---

*Analysis only — verify against vendor documentation before applying.*
