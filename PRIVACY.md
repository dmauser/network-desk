# Privacy

_Last updated: 2026-05-28 · Applies to: `@dmauser/network-desk` (the **Network Desk** Copilot CLI extension)_

## Summary (TL;DR)

Network Desk is a **local, read-only** Copilot CLI extension. It does **not** collect
telemetry, does **not** track usage, and does **not** transmit your prompts, code, or
generated files anywhere.

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
- ❌ No changes to your cloud infrastructure. All tools are read-only and deliver analysis
  (Markdown guidance) only.

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
