---
name: network-desk-sase
description: "🛡️ SASE / SSE — SASE / SSE. SASE architecture, ZTNA, SWG/CASB, SD-WAN integration, vendor comparison. Use for: SASE, SSE, zero, trust, ZTNA, secure, web, gateway, SWG, CASB, cloud, access, security, FWaaS."
metadata:
  specialist: sase-sse
  displayName: "🛡️ SASE / SSE"
  icon: "🛡️"
  domain: "SASE / SSE"
---

> **🛡️ SASE / SSE** · `network-desk-sase` · SASE / SSE

# 🛡️ SASE / SSE

SASE architecture, ZTNA, SWG/CASB, SD-WAN integration, vendor comparison.

## Scope & guidance

Covers SASE/SSE architecture, Zero Trust Network Access, SWG, CASB, SD-WAN integration, and vendor comparison (Zscaler, Palo Alto Prisma, Netskope, Microsoft, Cisco, Fortinet).

## Validation policy (Microsoft Learn MCP — Azure source of truth)

Validation-first: validate every Azure fact against the Microsoft Learn MCP server before stating it (Learn wins on conflict; cite the Learn URL). If no Learn MCP server is configured, label Azure answers ⚠️ unverified and suggest `copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`. AWS/GCP/firewall facts: verify against official vendor docs.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[architecture](./reference/architecture/SKILL.md)** — SASE/SSE architecture design — framework components, deployment models, migration from legacy VPN/proxy.
- **[ztna-design](./reference/ztna-design/SKILL.md)** — Zero Trust Network Access — identity-based access, app connectors, device posture, continuous trust.
- **[swg-casb](./reference/swg-casb/SKILL.md)** — Secure Web Gateway & CASB — URL filtering, TLS inspection, shadow IT, DLP, SaaS security posture.
- **[sdwan-integration](./reference/sdwan-integration/SKILL.md)** — SD-WAN with SASE integration — traffic steering, branch connectivity, QoS, vendor integrations.
- **[vendor-compare](./reference/vendor-compare/SKILL.md)** — SASE/SSE vendor comparison — Zscaler, Palo Alto Prisma, Netskope, Cisco, Microsoft, Fortinet.

---

*Analysis only — verify against vendor documentation before applying.*
