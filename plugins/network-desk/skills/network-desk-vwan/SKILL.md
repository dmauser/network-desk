---
name: network-desk-vwan
description: "🌍 Virtual WAN / SD-WAN — Virtual WAN / SD-WAN. vWAN/secured-hub design, routing intent, NVA, branch connectivity. Use for: Virtual, WAN, vWAN, VWAN, routing, intent, secured, hub, inter."
metadata:
  specialist: vwan-sdwan
  displayName: "🌍 Virtual WAN / SD-WAN"
  icon: "🌍"
  domain: "Virtual WAN / SD-WAN"
---

> **🌍 Virtual WAN / SD-WAN** · `network-desk-vwan` · Virtual WAN / SD-WAN

# 🌍 Virtual WAN / SD-WAN

vWAN/secured-hub design, routing intent, NVA, branch connectivity.

## Scope & guidance

Covers Azure Virtual WAN hubs, routing intent, and SD-WAN partner integrations.

## Validation policy (Microsoft Learn MCP — Azure source of truth)

Validation-first: validate every Azure fact against the Microsoft Learn MCP server before stating it (Learn wins on conflict; cite the Learn URL). If no Learn MCP server is configured, label Azure answers ⚠️ unverified and suggest `copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`. AWS/GCP/firewall facts: verify against official vendor docs.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[vwan-design](./reference/vwan-design/SKILL.md)** — Virtual WAN topology design — hubs, connections, secured hubs, inter-hub routing.
- **[secured-vhub-design](./reference/secured-vhub-design/SKILL.md)** — Azure Secured Virtual Hub design — when to use vs hub-spoke+NVA, routing intent, Azure Firewall vs partner NVA SKU selection, rule set design, forced-tunneling, HA & cross-region, observability, cost, common pitfalls.
- **[routing-intent](./reference/routing-intent/SKILL.md)** — Routing intent and routing policies — internet traffic, private traffic, inter-hub.
- **[nva-integration](./reference/nva-integration/SKILL.md)** — NVA integration in vWAN — BGP peering, managed appliances, SD-WAN partners.
- **[branch-connectivity](./reference/branch-connectivity/SKILL.md)** — Branch connectivity — S2S VPN, P2S, ExpressRoute to vWAN.
- **[troubleshoot](./reference/troubleshoot/SKILL.md)** — Troubleshoot vWAN — effective routes, connection state, hub routing.

---

*Analysis only — verify against vendor documentation before applying.*
