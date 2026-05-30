# Privacy

_Last updated: 2026-05-29 · Applies to: `@dmauser/network-desk` (the **Network Desk** Copilot CLI extension)_

## Summary (TL;DR)

Network Desk is a **local, mostly read-only** Copilot CLI extension. It does **not** collect
telemetry, does **not** track usage, and does **not** transmit your prompts, code, or
generated files anywhere. The single tool that writes to disk (`cn_mcp_install`) is opt-in
and requires the host's per-call approval prompt — see
[Vendor MCP servers](#vendor-mcp-servers-source-of-truth-guidance).

The extension makes **exactly one** outbound network request: a once-per-24-hours version
check against the project's public GitHub manifest. You can turn this off with a single
environment variable. Everything else it does happens entirely on your machine.

---

## What data the extension accesses

- **Your prompt text**, locally and in-memory only, to decide which networking specialist
  should handle a request. This is done with simple keyword/regex matching inside the
  `onUserPromptSubmitted` hook. The result is a short routing hint that is fed back into the
  **same local Copilot session** — it is never sent off your machine by the extension.
- **Bundled specialist content** (Markdown role and skill files shipped with the extension),
  read from local disk and returned to the Copilot session when you engage a specialist.
- **The Copilot CLI MCP config file** at `~/.copilot/m-mcp-servers.json` (Windows:
  `%USERPROFILE%\.copilot\m-mcp-servers.json`), read **read-only** by the `cn_mcp_doctor`
  tool to detect which vendor MCP servers are installed. The file's contents stay on your
  machine; only a derived report (counts, server names, and recommended additions) is
  returned to the Copilot session. Network Desk **never writes** this file unless you
  explicitly invoke `cn_mcp_install` and approve the host's per-call permission prompt.
- **The current working directory**, only when you (or the agent on your behalf) explicitly
  save a generated artifact — see [Files written locally](#files-written-locally).

## What leaves your machine

A single outbound request, used only to tell you when a newer version is available:

- **Request:** `GET https://raw.githubusercontent.com/dmauser/network-desk/master/package.json`
- **Frequency:** at most once every 24 hours, triggered at session start.
- **Payload:** none. No request body and no query parameters are sent.
- **Headers:** only a static `user-agent: network-desk-extension`.
- **Behavior:** non-blocking, 4-second timeout, and wrapped so any failure is silent — it
  never blocks or crashes your session.

As with **any** HTTPS request, GitHub (the host of `raw.githubusercontent.com`) necessarily
receives the network-level metadata inherent to the connection, such as your IP address. The
extension itself adds **no** identifying information beyond the static user-agent above.

## What the extension does NOT do

- ❌ No telemetry, analytics, or usage tracking.
- ❌ No transmission of your prompts, conversation, code, or generated files.
- ❌ No collection or sale of personal data.
- ❌ No accounts, no API keys, no credentials required or stored by the extension.
- ❌ No external runtime dependencies — the extension uses only the GitHub Copilot SDK and
  Node.js built-in modules, which keeps the supply-chain surface minimal.
- ❌ No changes to your cloud infrastructure. All specialist tools are read-only and
  deliver analysis (Markdown guidance) only. The single exception is `cn_mcp_install`,
  an opt-in writer for `~/.copilot/m-mcp-servers.json` that requires the host CLI's
  per-call approval prompt — see [Vendor MCP servers](#vendor-mcp-servers-source-of-truth-guidance).

## Files written locally

These files stay on your machine and are **never transmitted**:

- `.install-meta.json` (in the install directory) — records the installed version, install
  type, install timestamp, and source. Created by the installer.
- `.update-check.json` (in the install directory) — records the last update-check timestamp
  and the latest/installed versions, used to throttle the 24-hour check.
- **Generated artifacts** you ask a specialist to produce (diagrams, reports, configs) are
  written only inside your current working directory, under
  `network-desk/<specialist>/{diagrams,reports,configs}/`, and only when you request them.

## Controls and opt-out

- **Disable the update check entirely:** set the environment variable
  `NETWORK_DESK_NO_UPDATE_CHECK=1`. With this set, the extension makes **no** outbound
  network requests at all.
- **Uninstall:** run `network-desk uninstall` (or remove the extension directory) to remove
  the extension and its local state files.

## Vendor MCP servers (source-of-truth guidance)

Network Desk specialists are **instructed to prefer vendor MCP servers** (Microsoft Learn,
Azure MCP, AWS MCP, GCP MCP, Terraform MCP, GitHub MCP, Context7, and firewall-vendor
MCPs where available) as the source of truth for vendor documentation and live-tenant
queries. This is delivered as **guidance text** inside the Markdown that
`cn_role` / `cn_orchestrate` / `cn_skill` / `cn_sources` return — **Network Desk itself
does not call any MCP server.** The decision to call an MCP, and the actual call, are
made by the **host Copilot CLI agent** using whatever MCP tools you have separately
installed and configured.

The `cn_mcp_doctor` tool **reads** `~/.copilot/m-mcp-servers.json` (read-only) to detect
which MCP servers are configured and loaded, and returns a report with copy-pasteable
JSON snippets you can merge yourself. **It does not modify the file**, and it makes
**no network calls** of its own. The doctor's output (server names, tool counts, install
URLs we ship in the extension) is returned to the Copilot session like any other
extension tool result and stays on your machine unless you choose to share it.

### Opt-in writer (`cn_mcp_install`)

Network Desk ships **one optional write tool**, `cn_mcp_install`, which merges a
recommended MCP server snippet into `~/.copilot/m-mcp-servers.json` so you do not have
to copy-paste it yourself. This is the **only** Network Desk tool that writes to disk,
and it is explicitly opt-in:

- Every call requires the host Copilot CLI's **per-call Approve / Deny prompt**
  (`skipPermission: false`); Network Desk cannot bypass it.
- It **never overwrites** an existing server entry unless you pass `force: true`.
- Before each write it saves a timestamped backup at
  `~/.copilot/m-mcp-servers.json.backup-<ISO-timestamp>` and writes the new content
  atomically (`*.tmp` + rename) so a crash mid-write cannot corrupt the file.
- It makes **no network calls**; it only adds a JSON fragment shipped inside this
  extension. You still need to run any vendor-side steps (`docker pull`, `npm install`,
  authentication) yourself, and to restart the Copilot CLI to load the new tools.
- The snippets are listed in `MCP_INSTALL_SNIPPETS` in `extension.mjs`. You can audit
  them before approving any call.

If you do not want this capability at all, simply never approve the prompt — the doctor
(`cn_mcp_doctor`) and all specialist tools remain fully functional and read-only.

What this means in practice:

- ✅ Network Desk's own outbound footprint is unchanged: still **at most one** request
  per 24 hours to GitHub for the version check.
- ⚠️ If you have an MCP server installed (e.g. Azure MCP, Microsoft Learn MCP), the
  host agent may, in response to Network Desk's guidance, send your query and related
  context to that MCP server. **Data sent to a third-party MCP is governed by that
  server's own privacy policy and trust boundary**, not by this document.
- 🛑 If you have no MCP server installed, the guidance is a no-op — the agent simply
  falls back to baked-in knowledge with a "not validated against live vendor MCP"
  disclaimer. No additional network traffic is generated by Network Desk.
- 🔧 You control which MCPs are installed and whether the agent may call them. Network
  Desk only *recommends*; it cannot reach an MCP on its own.

If you need to suppress MCP-first guidance entirely, omit MCP servers from your CLI
configuration — Network Desk's guidance becomes inert without them.

## Relationship to GitHub Copilot CLI

Network Desk runs **inside** the GitHub Copilot CLI. The CLI host — not this extension — is
responsible for sending your conversation to the underlying AI model and operates under
**GitHub's own privacy terms**. This document covers only the behavior of the Network Desk
extension. For how Copilot itself handles your data, see:

- GitHub Privacy Statement — <https://docs.github.com/site-policy/privacy-policies/github-privacy-statement>
- GitHub Copilot Trust Center — <https://resources.github.com/copilot-trust-center/>

## Changes to this policy

Material changes to data handling will be reflected in this file and noted in
[`CHANGELOG.md`](CHANGELOG.md). The "Last updated" date above tracks the latest revision.

## Contact

Questions or concerns? Open an issue at
<https://github.com/dmauser/network-desk/issues>.
