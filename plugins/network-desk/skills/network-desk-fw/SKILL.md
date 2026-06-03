---
name: network-desk-fw
description: "🔥 Firewall Engineer — Firewall Engineering. Rule audits, policy design/test, vendor migration, config gen, HA, log analysis (14 vendors). Use for: firewall, rule, policy, PAN, FortiGate, FortiOS, Check, Point, CloudGuard, ASA, FTD, Firepower, SRX, Zscaler."
metadata:
  specialist: firewall-engineer
  displayName: "🔥 Firewall Engineer"
  icon: "🔥"
  domain: "Firewall Engineering"
---

> **🔥 Firewall Engineer** · `network-desk-fw` · Firewall Engineering

# 🔥 Firewall Engineer

Rule audits, policy design/test, vendor migration, config gen, HA, log analysis (14 vendors).

## Scope & guidance

Covers 14 vendor platforms: Azure Firewall, AWS Network Firewall, GCP Cloud Firewall, Palo Alto, FortiGate, Check Point, Cisco ASA/FTD, Juniper SRX, Zscaler, Sophos XG, OPNsense, pfSense, VyOS, iptables/nftables. Analysis only — never apply changes without confirmation.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[rule-audit](./reference/rule-audit/SKILL.md)** — Audit firewall rules for shadow rules, overly permissive entries, unused rules, hit-count analysis. Multi-vendor.
- **[policy-design](./reference/policy-design/SKILL.md)** — Design firewall policies from requirements — zone-based, app-aware, or L3/L4. Multi-vendor.
- **[policy-test](./reference/policy-test/SKILL.md)** — Validate firewall rules before/after deploy — vendor simulators, log-driven shadow testing, automated rule-coverage test cases, pre-deployment checklist.
- **[vendor-migrate](./reference/vendor-migrate/SKILL.md)** — Migrate firewall rules between vendor platforms (e.g., PAN-OS → FortiGate, ASA → Azure Firewall).
- **[config-gen](./reference/config-gen/SKILL.md)** — Generate vendor-specific firewall configuration from a policy intent description.
- **[hardening-check](./reference/hardening-check/SKILL.md)** — Security hardening checklist per vendor best practices.
- **[ha-design](./reference/ha-design/SKILL.md)** — Firewall high-availability design per vendor — active/passive, active/active, clustering.
- **[log-analysis](./reference/log-analysis/SKILL.md)** — Parse and analyze firewall logs (syslog, CEF, LEEF) for security events.
- **[troubleshoot](./reference/troubleshoot/SKILL.md)** — Troubleshoot firewall connectivity — packet flow, NAT, routing, policy lookup. Multi-vendor.

---

*Analysis only — verify against vendor documentation before applying.*
