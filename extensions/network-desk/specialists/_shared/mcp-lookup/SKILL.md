# Shared Skill: MCP-First Source-of-Truth Playbook

## Purpose

Network Desk specialists prefer **vendor MCP servers** as the source of
truth over baked-in knowledge. This shared playbook describes the
probe → query → fallback workflow every specialist uses, the MCP
servers Network Desk recognises, and how to handle the case where no
MCP is installed.

This file is loaded by the `cn_sources` tool and referenced from every
specialist's orchestration output via the `## Authoritative Sources
(MCP-first)` block.

---

## Core workflow

For every networking question — before you reason from internal
knowledge — perform these steps:

1. **Probe.** Inspect the agent's currently-available tool list for any
   tool whose name starts with one of the recognised MCP prefixes
   below. If a relevant MCP is available, treat its output as
   authoritative.
2. **Query.** Issue the smallest useful query against the MCP — usually
   a documentation search keyed on the exact resource/setting/error
   string the user mentioned. Prefer official-docs MCPs over generic
   ones, and prefer **live-tenant** MCPs (e.g. `azmcp_*`) when the
   user asks about *their* environment, not the product in general.
3. **Cite.** When you use MCP-returned content in an answer, name the
   MCP server in-line (e.g. *"per Microsoft Learn MCP, …"*) and
   include the doc URL the MCP returned.
4. **Fallback.** If no relevant MCP is available, answer from the
   baked-in skill knowledge, and append on its own line:
   `> Not validated against live vendor MCP — verify before applying.`
5. **Footer.** Always end the response with the canonical footer:
   `Analysis only — verify against vendor MCP / documentation before applying.`

This is **SHOULD-strength**: never block a response because no MCP is
installed. Just disclose it.

---

## Recognised MCP servers

| Key | Server | Typical tool prefixes | Best for | Install pointer |
|---|---|---|---|---|
| `microsoft-learn` | Microsoft Learn MCP | `microsoft_docs_*`, `microsoft.docs.*` | Azure, Entra, M365, .NET, Windows official docs | https://learn.microsoft.com/training/support/mcp |
| `azure-mcp` | Azure MCP (azmcp) | `azmcp_*` | Live tenant queries — subscriptions, resource groups, Key Vault, storage, monitor, KQL | https://github.com/Azure/azure-mcp |
| `aws-mcp` | AWS Labs MCP servers | `awslabs_*`, `aws_*` | AWS docs, CDK, Terraform AWS provider, service APIs | https://github.com/awslabs/mcp |
| `gcp-mcp` | Google Cloud MCP family | `gcp_*`, `googlecloud_*`, `cloudrun_*` | GCP resources, Cloud Run, BigQuery, GCP docs | https://github.com/GoogleCloudPlatform/cloud-run-mcp |
| `terraform-mcp` | HashiCorp Terraform MCP | `terraform_*` | Provider schemas, registry modules, resource docs across all clouds | https://github.com/hashicorp/terraform-mcp-server |
| `github-mcp` | GitHub MCP | `github_*` | Repos, issues, PRs, Actions, gh CLI docs | https://github.com/github/github-mcp-server |
| `context7` | Context7 MCP | `context7_*`, `c7_*` | Generic vendor / library docs fallback (Palo Alto, Fortinet, Cisco, Juniper, Zscaler, Sophos, OPNsense, pfSense, VyOS, …) | https://github.com/upstash/context7 |
| `firewall-vendors` | Vendor-specific firewall MCPs | varies (e.g. `panos_*`, `fortios_*`, `checkpoint_*`) | Live config / docs for that specific firewall vendor | Vendor-published; emerging — many vendors have no MCP yet, fall back to `context7` |

---

## Per-domain consultation order

Specialists declare their consultation order in `REGISTRY.<prefix>.mcpSources`
in `extension.mjs`. The order encodes which MCP to try **first** for
that domain — e.g. firewall questions consult vendor MCPs before
cloud-provider MCPs; IaC questions consult `terraform-mcp` first; the
report-builder specialist (`cn_doc`) consults none because it only
packages other specialists' findings.

Always honour the declared order. Do not query every MCP on the list
— stop as soon as one returns an authoritative answer.

---

## Probing for MCP availability

You cannot enumerate other extensions' tools directly, but you can
detect them by attempting a benign call. Two practical patterns:

- **Implicit probe.** Phrase the response plan as "if `microsoft_docs_search`
  is available, query it for *X*; otherwise …". The runtime will surface
  whichever tools exist; if none match, the conditional branch is
  skipped.
- **Explicit hint.** When the user asks a question whose answer
  benefits from a specific MCP (e.g. "what's the latest AVNM feature
  for hub-and-spoke?"), tell the user once which MCP would help and
  link the install pointer above.

Do **not** invent tool names. Do **not** claim to have queried an MCP
you did not actually call.

---

## Disclaimer wording

When falling back to baked-in knowledge:

> Not validated against live vendor MCP — verify before applying.

When the user is on a live tenant and you used `azmcp_*` (or any
`*-mcp` live-tenant tool):

> Sourced from live tenant via the Azure MCP server at <UTC timestamp>.

When you used a docs MCP:

> Sourced from <Microsoft Learn MCP | AWS docs MCP | …> documentation.

---

**Analysis only — verify against vendor MCP / documentation before applying.**
