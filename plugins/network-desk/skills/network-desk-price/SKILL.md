---
name: network-desk-price
description: "💰 Pricing Analyst — Network Pricing. Egress/VPN/circuit/LB/firewall pricing, cross-cloud cost compare & optimization. Use for: pric, ing, cost, estimat, compar, analy, optim, break, egress, data, transfer, TCO, total, billing."
metadata:
  specialist: pricing-analyst
  displayName: "💰 Pricing Analyst"
  icon: "💰"
  domain: "Network Pricing"
---

> **💰 Pricing Analyst** · `network-desk-price` · Network Pricing

# 💰 Pricing Analyst

Egress/VPN/circuit/LB/firewall pricing, cross-cloud cost compare & optimization.

## Scope & guidance

Covers Azure, AWS, and GCP networking costs. Prices are indicative — always verify against current vendor pricing pages.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[egress-calc](./reference/egress-calc/SKILL.md)** — Data transfer and egress cost calculation across Azure, AWS, and GCP — tiered pricing, inter-region, peering costs.
- **[egress-architecture](./reference/egress-architecture/SKILL.md)** — Architectural patterns to structurally reduce egress cost — PrivateLink/Gateway Endpoints, CDN offload, regional pinning, dedicated interconnects, commit discounts. Break-even modeling.
- **[vpn-pricing](./reference/vpn-pricing/SKILL.md)** — VPN gateway pricing comparison — per-hour costs, tunnel limits, data transfer charges across all three clouds.
- **[circuit-pricing](./reference/circuit-pricing/SKILL.md)** — Dedicated circuit pricing — ExpressRoute, Direct Connect, Cloud Interconnect fees, break-even analysis vs VPN.
- **[lb-pricing](./reference/lb-pricing/SKILL.md)** — Load balancer pricing — Azure LB/AppGW/Front Door, AWS ALB/NLB/GLB, GCP LB cost structures.
- **[firewall-pricing](./reference/firewall-pricing/SKILL.md)** — Firewall pricing — Azure Firewall tiers, AWS Network Firewall, GCP Cloud Armor, NVA marketplace costs.
- **[cost-optimizer](./reference/cost-optimizer/SKILL.md)** — Network cost optimization — reduce egress, right-size gateways, reserved capacity, architectural patterns to save.
- **[price-compare](./reference/price-compare/SKILL.md)** — Cross-cloud network pricing comparison — side-by-side tables for equivalent services, workload scenario costs.

---

*Analysis only — verify against vendor documentation before applying.*
