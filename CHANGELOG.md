# Changelog

All notable changes to **@dmauser/network-desk** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [2.2.0] - 2026-06-07

### Changed

- **Report Builder renderers refactored into professional whitepaper output.** The Word
  renderer (`make_docx.py`) is no longer a Markdown dump — it now produces a real cover
  page, true inline formatting, and embedded diagrams, with the PDF/HTML renderers brought
  to parity.
  - **New shared helper module `renderers/_common.py`** (dependency-free): HTML-entity
    decoding, output-path/`diagrams/` resolution, a minimal `key: value` **YAML
    front-matter** parser (no PyYAML), emoji stripping that **preserves technical arrows**
    (`->`, `→`), cover-page resolution, and the local-only Mermaid → PNG bridge plus shared
    cover/figure/appendix HTML builders.
  - **Cover page** sourced by precedence **front-matter → `--title`/`--subtitle`/
    `--classification`/`--version`/`--author` flags → first `# H1`** (never `--specialist`):
    title + subtitle + colored accent rule + Classification/Version/Author/Date metadata.
  - **Real inline runs everywhere:** `**bold**`, `*italic*`, `` `code` ``, `~~strike~~`,
    and clickable `[text](url)` hyperlinks render as actual Word runs in paragraphs,
    headings, list items, blockquotes, and table cells — no literal `**`, backticks, or
    `[]()` survive. Entities are decoded.
  - **Mermaid → embedded PNG** via the **local Mermaid CLI only** (`mmdc`, falling back to
    `npx -y @mermaid-js/mermaid-cli`): centered ~6.3in image with a "Figure N." caption;
    `.mmd`/`.png` saved under `network-desk/<specialist>/diagrams/`. When the CLI is
    unavailable it emits "[diagram omitted]", lists the source in an **Appendix: Diagram
    Sources**, and prints the exact install command — never an inline dump, never a hosted
    service. HTML/PDF base64-embed the PNG so output stays self-contained.
  - **Styling:** Calibri theme, navy Title/Heading 1, blue Heading 2/3 + subtitle + accent
    rule, shaded navy table header rows; real Word styles (Heading 1/2/3, List
    Bullet/Number, Quote, Table Grid); a TOC field and a footer **live PAGE field** (Word
    rebuilds both on open via `updateFields`).
  - DOCX dependencies remain **python-docx + markdown-it-py only**. Updated the
    `docx-report` and `report-structure` skill docs accordingly.

### Added

- **Pricing Analyst now fetches live prices as the source of truth (never hard-coded/cached rates).**
  Every numeric cloud price MUST be retrieved from a live pricing API and cited before it is used in
  any calculation; only clearly-flagged `INDICATIVE` values are allowed when an API is unreachable.
  - **New `retail-prices-api` skill** documenting the **Azure Retail Prices API**
    (`https://prices.azure.com/api/retail/prices`, anonymous): OData `$filter` patterns for
    Bandwidth/egress, VPN/ExpressRoute gateways, Load Balancer/App Gateway, Azure Firewall, NAT
    Gateway, Public IP, Front Door, Private Link, DNS; region/SKU/meter selection; `NextPageLink`
    paging; tiered-egress + monthly-free-allowance modelling; response fields to cite
    (`retailPrice`, `unitOfMeasure`, `armRegionName`, `armSkuName`, `meterName`, `effectiveStartDate`,
    …); curl / PowerShell / Python examples; Consumption-vs-1yr-vs-3yr-RI comparison. Multi-cloud:
    **AWS** Price List Query API (`GetProducts`) and **GCP** Cloud Billing Catalog API are
    authoritative for their clouds.
  - `registry.mjs`: registered the skill, rewrote `price.guidance` into a mandatory live-fetch
    directive (echo `$filter`, region, SKU/meter, `retailPrice`, `effectiveStartDate`, currency,
    retrieval timestamp), and extended `price.trigger` (retail price, list price, $/GB, per-GB,
    hourly rate, egress price).
  - Propagated a top-of-workflow "source all Azure rates from `retail-prices-api` before calculating;
    do not embed static rates" line into the egress-calc, egress-architecture, vpn-pricing,
    circuit-pricing, lb-pricing, firewall-pricing, cost-optimizer, and price-compare skills, plus the
    Pricing Analyst agent guardrail.
  - Report Builder XLSX cost-model guidance now requires the Inputs sheet's Azure rates to come from
    `retail-prices-api`, recording `armSkuName`, region, `meterName`, currency, and
    `effectiveStartDate` in a Source column (placeholders only when the API was unreachable, flagged).

- **Validation-first: each cloud's official documentation MCP is now the primary source of truth.**
  When the relevant docs MCP server is configured, specialists MUST validate every networking fact
  (service SKUs/tiers, limits & quotas, regional availability, feature support, pricing dimensions,
  API/CLI/IaC syntax & versions) against that cloud's docs **before** stating it, treat the docs MCP
  as authoritative (it overrides built-in/model knowledge on conflict), and cite the exact doc URL(s).
  - **Per-cloud servers + setup commands:**
    - **Azure** → Microsoft Learn MCP (hosted HTTP):
      `copilot mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`
    - **AWS** → AWS Documentation MCP (local stdio; needs `uv`/`uvx` + Python ≥3.10):
      `copilot mcp add aws-docs --env FASTMCP_LOG_LEVEL=ERROR --env AWS_DOCUMENTATION_PARTITION=aws -- uvx awslabs.aws-documentation-mcp-server@latest`
    - **GCP** → configurable placeholder: `copilot mcp add gcp-docs -- <your-gcp-docs-mcp-command>`
  - **Degraded (unverified) mode:** when a cloud's docs MCP is unreachable, that cloud's answers are
    prepended with a ⚠️ "Unverified — <server> not configured" banner, numeric specs/limits are
    marked *indicative, unverified*, and the response includes the matching `copilot mcp add` command.
  - **Scope:** each docs MCP covers its own cloud only — firewall-vendor facts are validated against
    official vendor docs and keep the standard analysis-only guardrail.
  - The policy is centralized in `extensions/network-desk/registry.mjs` (`MCP_PROVIDERS` +
    `MCP_VALIDATION_DIRECTIVE` + `mcpFallbackBanner()`/`MCP_FALLBACK_BANNER` + `MCP_VALIDATION_NOTE`)
    and surfaced by both the SDK extension (`cn_role`/`cn_skill`/`cn_orchestrate` loads, the session
    presence note, and the prompt hook on any specialist match) and the generated native plugin
    (coordinator agent + every specialist `SKILL.md`). Regenerate the plugin via
    `network-desk plugin build`. Network Desk never edits your MCP configuration — it is a per-user
    CLI setting you manage yourself.

- **Text/ASCII topology diagrams are now the console default (vnet-architect).** New
  `vnet_skill_ascii_diagram` skill renders network topologies as plain-text/ASCII using
  box-drawing characters — zero rendering setup, works in any terminal, SSH session, or
  plaintext chat. It is the default format for topologies shown inline in the console, with
  templates for hub-spoke, multi-region, and AWS Transit Gateway layouts.
  - **Mermaid, Excalidraw, and draw.io are now opt-in richer formats** offered after the ASCII
    diagram (previously Mermaid was the default). The vnet-architect `guidance`, role definition
    (Step 5), `network-diagram`/`drawio-diagram`/`excalidraw-diagram` skill headers, and the
    registry `summary` were updated accordingly. Regenerate via `network-desk plugin build`.

- **Native Copilot CLI plugin (second install option).** Network Desk can now be installed as a
  native `copilot plugin` in addition to the SDK extension. The plugin ships **one coordinator
  agent** (`Network Desk`) that routes to **20 specialist skills**, with each specialist's deep
  sub-skill docs bundled under `reference/` for on-demand loading. Routing in plugin form is
  LLM-driven (vs. the extension's deterministic regex hooks); both forms deliver the same
  specialist depth.
  - New CLI commands: `network-desk init --plugin` (registers a local marketplace then installs via
    `copilot`), `network-desk plugin build` (regenerates the bundle), and
    `network-desk uninstall --plugin`. `network-desk status` now reports plugin-bundle presence.
  - The plugin bundle is **generated from the same single source of truth** as the extension:
    `REGISTRY` was extracted into a dependency-free [`extensions/network-desk/registry.mjs`](extensions/network-desk/registry.mjs)
    (imported by `extension.mjs`) and the generator
    [`extensions/network-desk/scripts/build-plugin.mjs`](extensions/network-desk/scripts/build-plugin.mjs)
    emits [`plugins/network-desk/`](plugins/network-desk/) and a repo-level
    `.github/plugin/marketplace.json`. No specialist content is hand-forked.
  - README: new "Install as a native Copilot CLI plugin" section + extension-vs-plugin comparison.
  - Plugin skills carry their emoji icon and friendly specialist name in the skill `description`
    and `metadata` (`displayName`/`icon`), and the coordinator agent is instructed to render skill
    listings as an emoji + friendly-name table — so dumping the skill table reads cleanly instead of
    showing bare `network-desk-*` ids.

- **Privacy documentation** — added [`PRIVACY.md`](PRIVACY.md) describing exactly how the
  extension handles data: it collects no telemetry, transmits no prompts/code/files, and makes
  only a single optional once-per-24h GitHub version check (disable with
  `NETWORK_DESK_NO_UPDATE_CHECK=1`). Referenced from the README and shipped with the package.

---

## [2.0.0] - 2026-05-28

### Changed — ⚠️ BREAKING: renamed the extension to **Network Desk**

The project, npm package, extension directory, CLI command, `@mention` trigger, and GitHub repository were renamed from `cloud-networking` to `network-desk`.

- **npm package:** `@dmauser/cloud-networking` → `@dmauser/network-desk`.
- **Mention trigger:** `@cloud-networking` → `@network-desk` (the matcher also accepts `network desk` / `networkdesk`).
- **CLI command & install paths:** `cloud-networking` → `network-desk` (installs to `~/.copilot/extensions/network-desk/` and `.github/extensions/network-desk/`).
- **Output-file convention folder:** generated artifacts now save under `network-desk/<specialist>/{diagrams,reports,configs}/`.
- **Environment variables:** `CLOUD_NETWORKING_NO_UPDATE_CHECK` → `NETWORK_DESK_NO_UPDATE_CHECK`; `CLOUD_NETWORKING_VALIDATE` → `NETWORK_DESK_VALIDATE`.
- **GitHub repo:** `dmauser/cloud-networking` → `dmauser/network-desk` (GitHub preserves redirects from the old URL).
- The tool prefix (`cn_`) and specialist aliases (`cn_vnet`, `cn_fw`, …) are **unchanged** to avoid breaking existing routing/invocations.

### Added — Report Builder specialist (`cn_doc`)

A new packaging specialist that turns any other specialist's analysis into a polished, shareable deliverable. It does **not** perform networking analysis itself — it structures and renders findings.

- New specialist `report-builder` (`cn_role({ specialist: "cn_doc" })`), bringing the team to **20 specialists**. No new tools are added — it is served by the existing 5 parameterized tools (well under the 128-tool API limit).
- Five skills: `report-structure` (audience-aware report layout), `html-report`, `pdf-report`, `docx-report`, and `xlsx-workbook` (real-formula spreadsheet models with named ranges).
- Wires the previously orphaned `renderers/make_{html,pdf,docx,xlsx}.py` into a discoverable workflow. Skills include ordered renderer-path discovery and a dependency-fallback path (degrade to Markdown/HTML when a Python lib is missing).
- The session presence note now points specialists at `cn_doc` for packaging findings, and routing recognizes report/export intents (e.g. "generate a PDF report") while ignoring incidental uses of "report" (e.g. "report packet loss").

### Added — Standard output-file layout for generated artifacts

Generated diagrams, reports, and configs now follow one predictable on-disk structure under a `network-desk/` folder in the current working directory:

```
network-desk/<specialist>/diagrams/   # .mmd, .excalidraw, .drawio
network-desk/<specialist>/reports/    # .md, .html, .pdf, .docx, .xlsx
network-desk/<specialist>/configs/    # generated IaC, device configs, scripts
```

- `<specialist>` is the kebab-case specialist name (e.g. `vnet-architect`, `firewall-engineer`). Files are named `<kebab-topic>-<YYYYMMDD>.<ext>`.
- The convention is injected via the session presence note, so every specialist that writes a file follows it.
- The diagram skills (`network-diagram`, `excalidraw-diagram`, `drawio-diagram`) now instruct saving under `network-desk/vnet-architect/diagrams/`.
- The report renderers (`make_html.py`, `make_pdf.py`, `make_docx.py`, `make_xlsx.py`) now make `--output` optional, defaulting to `network-desk/<specialist>/reports/<stem>.<ext>`, with a new `--outdir` to override the base folder.

### Changed — Extension runtime performance

Surgical performance improvements to `extension.mjs` (no behavior change to tool output):

- **Startup registry validation is now opt-in and concurrent.** `validateRegistry()` previously read all ~138 role/skill `.md` files serially from disk on every session start. It now runs only when `NETWORK_DESK_VALIDATE=1` (a dev-time check; published installs are static and covered by tests) and, when enabled, performs its file checks in parallel via `Promise.all`.
- **In-memory file cache.** Role/skill files are immutable for a session, so `loadFile()` now caches successful reads, avoiding repeat disk I/O on subsequent `cn_role`/`cn_skill` calls. Failures are not cached.
- **Memoized capabilities summary.** `buildCapabilitiesSummary()` is derived only from the static `REGISTRY`; it is now computed once and reused across `cn_capabilities` calls.

### Changed — Specialist content audit: 2026 currency, consistency, and guardrail normalization

A repo-wide best-practices audit of all 19 specialists and 119 skills (web-verified against current vendor documentation) drove **109 fixes** (4 critical, 45 high, 33 medium, 27 low) across 128 markdown files. Highlights:

- **Azure NSG flow logs → VNet flow logs**: reframed across network-monitor, network-troubleshooter, capacity-planner, private-link, and network-security (new NSG flow log creation blocked after 2025-06-30; retirement 2027-09-30).
- **Corrected capacity/limit errors** (de-risked to per-resource quotas + "verify current quotas"): Azure NAT Gateway throughput (per-resource, not × IP count; Standard 50 / StandardV2 100 Gbps), AWS NAT Gateway connection/pps model, AWS Transit Gateway 100 Gbps per VPC attachment per AZ, GCP Cloud VPN packet-rate framing.
- **AWS PrivateLink cross-Region** access added (private-link, multi-cloud-net).
- **IaC/automation**: Terraform provider pins refreshed, S3 `use_lockfile` (DynamoDB locking deprecated), `tfsec` → Trivy, and a non-enforcing AWS SCP (`ec2:CreateRoute` with unsupported condition keys) replaced with an AWS Config / EventBridge detective control.
- **Retirements flagged**: Application Gateway v1, Azure CDN classic/Edgio (Front Door default), non-AZ VpnGw1-5 SKUs.
- **Currency**: AKS Azure CNI Overlay (no VXLAN; in-place `az aks update` migration), Gateway API `v1`, Azure/GCP IPv6 (StandardV2 NAT IPv6 outbound, GCP /64 subnet + /96 per NIC, AWS DNS64/NAT64), DNSSEC RFC 9824, AWS WAF rate/Bot Control limits, GCP Service Extensions/Media CDN, "Azure AD" → "Microsoft Entra ID".
- **Pricing skills de-risked**: brittle hardcoded rates replaced with date-stamped illustrative guidance + calculator links (corrected Azure 100 GB free egress tier, GCP Cloud NAT cost model, AWS public IPv4 charges).
- **Guardrail footer normalized**: every role + skill file (138/138) now ends with the canonical `**Analysis only — verify against vendor documentation before applying.**` (6 prior wordings unified; 12 missing footers added).
- **Wiring**: fixed two skill handoffs that referenced non-existent skills.

### Added — `cn_`-prefixed specialist ids, presence note, and stronger routing

- **Specialist ids are now `cn_`-prefixed** (`cn_vnet`, `cn_fw`, `cn_dns`, …) for a consistent namespace. They are the canonical value for the `specialist` argument and appear in all `cn_route` / `cn_capabilities` / `cn_orchestrate` output. The bare forms (`vnet`, `fw`, …) and directory names remain accepted as aliases, so nothing breaks.
- **Session-start presence note** (`onSessionStart`) announces the extension, its 19 specialists, and the discovery tools from turn 1 — so the agent never claims network-desk is unavailable. A belt-and-suspenders fallback re-injects it on the first prompt for older CLI builds.
- **Direct-mention handling**: naming the extension (`@network-desk`, or just "network-desk") injects an imperative instruction to call `cn_capabilities` first and offer concrete example prompts.
- **Per-specialist throttling**: each routing hint is injected at most once per session to avoid crowding the context window.
- **Hardened routing guidance**: the hook now uses imperative MUST language, requires calling the matched specialist's `cn_role` **before** answering (no answering from prior/general knowledge), and explicitly **prohibits reading the `specialists/**` files directly** — all specialist content must be loaded via `cn_role` / `cn_orchestrate` / `cn_skill`.
- **Specialist emoji icons** surfaced in `cn_capabilities`, `cn_orchestrate`, `cn_route`, the routing hints, and the README team table.
- Broadened the mention pattern to match `network-desk` with or without a leading `@`.

### Fixed — Exceeded the 128-tool API limit (extension failed to load)

The extension registered ~162 tools (per-specialist `*_role`, `*_orchestrate`, and ~121 `*_skill_*` tools). The Copilot CLI/model enforces a hard **128-tool limit**, so every request was rejected with *"Request failed due to a transient API error. Retrying..."* and the extension was unusable.

Tools are now **parameterized** instead of registered per specialist — **5 tools total**, well under the limit:

- `cn_capabilities` — full specialist/skill map
- `cn_route({ query })` — recommends the specialist(s) and the exact calls to make
- `cn_role({ specialist })` — loads the specialist role definition
- `cn_orchestrate({ specialist })` — returns the workflow + skill catalog
- `cn_skill({ specialist, skill })` — loads a specific skill's deep guidance

Other changes:

- Introduced a single `REGISTRY` object (prefix → `{ dir, domain, trigger, guidance, skills }`) as the source of truth; routing, capabilities, orchestration prompts, and skill loading are all generated from it.
- `cn_skill` tolerates legacy names (e.g. `vnet_skill_address_planner`) and underscores as the `skill` argument, normalizing them to kebab-case.
- Hook/orchestrator guidance now points only at the 5 parameterized tools and explicitly notes that legacy `*_role`/`*_skill_*` names are references, not callable tools.
- Added startup registry validation (verifies every role/skill `.md` exists, regexes compile, prefixes are unique) that logs issues without crashing.

No specialist or skill was removed — all 19 specialists and 119 skills remain available through the parameterized tools.

### Added — Tier 1 specialist coverage (10 new skills)

Implements the highest-priority "clear coverage gaps" identified in the specialist-improvement audit. All skills follow the standard template (purpose · decision tree · per-vendor reference · workflow · verification checklist · references) and end with the analysis-only guardrail.

| Specialist | New skill | Scope |
|---|---|---|
| firewall-engineer | `fw_skill_policy_test` | Rule simulation & dry-run before deploy. Azure FW Policy Analyzer, AWS NFW log testing, PAN `test security-policy-match`, FortiGate `diagnose firewall policy lookup`, Check Point `fw monitor`, Cisco `packet-tracer`, nftables/iptables. Log-driven shadow testing + automated rule-coverage test cases + pre-deployment checklist. |
| load-balancer | `lb_skill_tls_cert_mgmt` | Full cert lifecycle. Source selection (managed / ACME / public CA / private CA), storage (Key Vault / ACM / Secret Manager / cert-manager), per-LB deployment (AGW, Front Door, ALB, NLB, CloudFront, GCP HTTPS LB, NGINX, HAProxy), SNI strategy, ALPN, rotation, monitoring (3-tier expiry alerts), emergency revocation runbook. |
| dns-specialist | `dns_skill_dnssec_design` | DNSSEC end-to-end. Algorithm selection (default ECDSA P-256), KSK/ZSK/CSK, signing automation, NSEC3 RFC 9276 parameters, DS-record delegation flow, pre-publish ZSK rollover, double-DS KSK rollover, monitoring, emergency rollback. Azure DNS, Route 53, Cloud DNS, BIND9. |
| hybrid-connectivity | `hyb_skill_bgp_design` | Dedicated BGP. ASN allocation, prefix/AS-PATH/community filters, attribute manipulation (Local-Pref, prepend, MED), multi-circuit active/active and active/passive, BFD + GR, loop prevention, cloud-specific gotchas (Azure ExpressRoute/VPN, AWS DX/VPN, GCP Cloud Router). |
| network-security | `nsec_skill_zero_trust_architecture` | NIST SP 800-207 / CISA ZTMM v2.0 alignment. Seven pillars, PEP/PDP placement, identity-aware access, microsegmentation, east-west mTLS, egress control, DNS-as-control, continuous verification (CAE, AWS Verified Access), workload identity (SPIFFE / managed identities), threat model + anti-patterns. |
| network-security | `nsec_skill_waf_policy_design` | Cross-cloud WAF design. Five-layer model (managed rule sets → custom rules → rate limiting → bot management → geo/IP), Detect→Prevent rollout, OWASP CRS anomaly tuning, false-positive exclusion patterns, integration with CDN/DDoS/API gateway/ZTNA, logging+alerts. Azure WAF, AWS WAFv2, GCP Cloud Armor, Cloudflare, F5, Imperva, FortiWeb. |
| network-troubleshooter | `ntsh_skill_tls_handshake_debug` | Handshake failure debugging. Full IANA TLS-alert decoder table (40/42/48/51/112/116/120 etc.), `openssl s_client` / `testssl.sh` / `nmap ssl-enum-ciphers` workflows, cert-chain & SAN validation, SNI/ALPN/mTLS failure patterns, OCSP stapling, clock skew, middlebox interception, decryption via SSLKEYLOGFILE, QUIC/HTTP3. |
| vwan-sdwan | `vwan_skill_secured_vhub_design` | Azure Secured Virtual Hub patterns. When to use vs hub-spoke+NVA, routing-intent modes (internet/private/both), Azure Firewall vs partner NVA SKU selection, rule-set design, forced-tunneling, HA + cross-region, Private Endpoint inspection caveat, observability, cost model, common pitfalls. |
| network-monitor | `nmon_skill_synthetic_monitoring` | Proactive user-perspective probing. Azure Connection Monitor + App Insights availability tests; AWS CloudWatch Synthetics; GCP Uptime Checks; self-hosted Blackbox Exporter + Prometheus; global PoP vendors (Catchpoint, ThousandEyes, Datadog, Pingdom). Probe design principles, multi-region thresholds, SLO/SLI integration, dashboards, anti-patterns. |
| pricing-analyst | `price_skill_egress_architecture` | Structurally avoid egress charges. PrivateLink/Gateway Endpoints, CDN offload with cache discipline, regional pinning, cross-AZ minimization, dedicated interconnects break-even, egress-free storage tiers (R2, B2), compression/batching, multi-cloud peering exchanges, AWS NAT GW tax mitigation, commit-discount tiers. Quantified before/after modeling. |

Orchestrator prompts (`ORCHESTRATORS.fw`, `.lb`, `.dns`, `.hyb`, `.nsec`, `.ntsh`, `.vwan`, `.nmon`, `.price`) updated to include the new skill names so the routing layer engages them automatically.

### Added — Deep PCAP analysis skill (network-troubleshooter)
- New skill **`ntsh_skill_pcap_analysis`** dedicated to deep packet-capture analysis with Wireshark, tshark, and the surrounding toolchain (capinfos, editcap, mergecap, reordercap, text2pcap, Zeek, ngrep, pyshark/scapy).
- Complements (does not replace) `ntsh_skill_packet_capture`: capture-side mechanics stay there; analysis-side workflows move into the new skill. The orchestrator pairs the two automatically.
- Coverage: capture profiling (`capinfos`), tshark cheatsheet (TCP retransmissions, RTT, throughput, zero-window stalls, DNS latency, TLS handshake inspection, HTTP timing, fragmentation, microbursts), Wireshark Statistics & Expert Info navigation, six diagnostic playbooks (slow downloads, TLS failures, jitter, asymmetric routing, MTU, NAT/SNAT exhaustion), dual-point capture merging, decryption (TLS keylog, IPsec, WireGuard, Kerberos), anonymization for safe sharing, and cloud-specific PCAP source gotchas (Azure Network Watcher, AWS VPC Traffic Mirroring, GCP Packet Mirroring, container netns, service mesh sidecars).
- Updated `network-troubleshooter` agent to reference Wireshark/tshark/Zeek and point at the new skill.
- Tool count: 145 → 146.

### Added — Auto-update check and `update` command
- The extension now performs a **lightweight automatic update check** against GitHub on session start. Behavior: at most once every 24 h, ~4 s network timeout, fully async, never blocks extension load, fails silently on any error. When a newer version is detected, a one-line `network-desk: update available — installed X.Y.Z, latest A.B.C. Run \`npx github:dmauser/network-desk update\` to upgrade.` notice is written to the session log.
- Opt-out via `NETWORK_DESK_NO_UPDATE_CHECK=1` environment variable.
- New CLI command **`network-desk update`** (alias `upgrade`) — auto-detects whether the user has a user-level install, a project-level install, or both, and re-installs each in place by pulling the latest from `github:dmauser/network-desk`.
- New CLI flag **`network-desk --version`** / `-v` to print the installed CLI version.
- Install metadata is now recorded at `<install-dir>/.install-meta.json` (version, install type, install timestamp) at every `init` / `init --project`, and surfaced by `network-desk status`.
- README's "Updating" section rewritten to document the auto-check, the new `update` command, the opt-out env var, and a pointer to `CHANGELOG.md`.
- `.gitignore` updated to exclude the runtime `.install-meta.json` and `.update-check.json` files anywhere in the tree.

## [1.1.0] — 2026-05-18

### Added — `@network-desk` mention trigger
- New explicit invocation: type **`@network-desk`** anywhere in a prompt to engage the extension. The `onUserPromptSubmitted` hook recognizes the mention (case-insensitive, accepts `@network-desk`, `@cloud_networking`, `@cloudnetworking`) and always engages the router, even when no specialist keyword matches.
- When mentioned without a keyword match, the router instructs the model to silently call `cn_route` (and `cn_capabilities` if still ambiguous) to pick the right specialist before responding.
- Routing context now tells the model to respond in **natural language** rather than exposing internal tool names to the user.

### Added — Excalidraw and draw.io diagram skills (vnet-architect)
- `vnet_skill_excalidraw_diagram` — generates `.excalidraw` JSON (hand-drawn / whiteboard style), suitable for slides, workshops, and design reviews. Always prefers official Azure / AWS / GCP icon libraries from [libraries.excalidraw.com](https://libraries.excalidraw.com).
- `vnet_skill_drawio_diagram` — generates `.drawio` XML with native cloud-provider stencils (`mxgraph.azure2`, `mxgraph.aws4`, `mxgraph.gcp2`, `mxgraph.kubernetes`). Suitable for polished, presentation-ready architecture diagrams and PNG/SVG/PDF export.

### Changed — Diagram policy (Mermaid is the primary format)
- `vnet_skill_network_diagram` is now declared the **default** diagram format for every design output. It renders inline in GitHub, VS Code, and most chat clients with zero setup.
- New 3-tier icon-selection order, enforced across all three diagram skills:
  1. **Official cloud-provider icons** (Iconify refs in Mermaid `architecture-beta`: `logos:microsoft-azure`, `logos:aws`, `logos:google-cloud`, `logos:kubernetes`; native stencils in draw.io; community libraries in Excalidraw).
  2. **Emoji fallback** for clients that don't render Iconify or for vendor firewalls without stencils — full mapping table included (🛡️ firewall, 🔐 VPN gateway, ⚡ ExpressRoute, ⚖️ load balancer, 🌐 VNet, 🔒 PrivateLink, 🏢 on-prem, ☁️ internet, 🐳 container, …).
  3. **Plain text label** with the canonical product name as a last resort.
- Every Mermaid diagram now ends with a built-in offer to also generate the diagram as Excalidraw or draw.io on request — alternative formats are **opt-in** and never produced by default.
- Updated the `vnet-architect` agent persona and the VNet orchestrator prompt to enforce this policy.

### Changed — README and user-facing examples
- All usage examples rewritten as natural-language prompts prefixed with **`@network-desk ...`** (every specialist and every multi-domain example, ~60 examples in total).
- "How It Works" rewritten to highlight the `@network-desk` mention as the trigger — no more `cn_capabilities` / `cn_route` / `<prefix>_role` plumbing in user-facing documentation.
- "Discovery" section rewritten as natural-language asks ("what can you help me with?", "which specialists cover firewalls?").
- Quick Start now shows two natural-language invocation examples.
- Troubleshooting row about `cn_capabilities` replaced with one about `@network-desk` not engaging.
- New **Changelog** link in the table of contents.

### Internal
- Bumped tool count from 143 → 145 (two new diagram skills).
- Reinstalled to `~/.copilot/extensions/network-desk/` with `network-desk init`.

---

## [1.0.0]

### Added
- Initial public release of `@dmauser/network-desk`.
- 19 specialist agents covering VNet design, firewalls (14 vendors), load balancing, DNS, private link, hybrid connectivity, network security, troubleshooting, vWAN/SD-WAN, monitoring, multi-cloud, pricing, IaC, container networking, CDN/edge, network automation/GitOps, SASE/SSE, capacity planning, and IPv6 migration.
- Auto-routing hook (`onUserPromptSubmitted`) detecting networking keywords.
- Discovery tools `cn_capabilities` and `cn_route`.
- CLI installer with `init`, `init --project`, `status`, `uninstall` commands.
- Mermaid network diagram skill for vnet-architect.

---

[Unreleased]: https://github.com/dmauser/network-desk/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/dmauser/network-desk/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/dmauser/network-desk/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/dmauser/network-desk/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/dmauser/network-desk/releases/tag/v1.0.0
