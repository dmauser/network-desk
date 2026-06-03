---
name: network-desk-nauto
description: "🔄 Network Automation & GitOps — Network Automation & GitOps. CI/CD pipelines, drift detection, policy-as-code, testing, rollback. Use for: automat, GitOps, pipeline, drift, detect, policy, code, testing, rollback, terraform, automation, bicep."
metadata:
  specialist: network-automation
  displayName: "🔄 Network Automation & GitOps"
  icon: "🔄"
  domain: "Network Automation & GitOps"
---

> **🔄 Network Automation & GitOps** · `network-desk-nauto` · Network Automation & GitOps

# 🔄 Network Automation & GitOps

CI/CD pipelines, drift detection, policy-as-code, testing, rollback.

## Scope & guidance

Covers CI/CD pipelines for network changes, GitOps workflows, drift detection, policy-as-code, automated testing, and rollback strategies.

## Persona & workflow

Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines this specialist's identity, the deliverables to produce, and the step-by-step workflow to follow.

## Sub-skills (load on demand)

Each sub-skill below has a deep reference document under `reference/`. Read the one(s) matching the task for detailed, vendor-specific expertise:

- **[pipeline-design](./reference/pipeline-design/SKILL.md)** — CI/CD pipeline design for network IaC — GitHub Actions, Azure DevOps, stages, approvals, secrets.
- **[drift-detection](./reference/drift-detection/SKILL.md)** — Configuration drift detection — Terraform state drift, Resource Graph queries, AWS Config, remediation.
- **[policy-as-code](./reference/policy-as-code/SKILL.md)** — Policy-as-code — Azure Policy, OPA/Rego, Checkov, tfsec. Enforce network governance pre-deployment.
- **[testing](./reference/testing/SKILL.md)** — Network config testing — Terratest, Pester, pytest, smoke tests, integration tests, chaos engineering.
- **[rollback](./reference/rollback/SKILL.md)** — Rollback and change management — state rollback, blue-green, canary, blast radius control, validation gates.

---

*Analysis only — verify against vendor documentation before applying.*
