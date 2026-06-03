// Extension: network-desk (standalone)
// Self-contained cloud networking agent that bundles all specialist
// roles and skills. No external extension dependencies required.
//
// Specialists: vnet-architect, firewall-engineer, load-balancer,
// dns-specialist, private-link, hybrid-connectivity, network-security,
// network-troubleshooter, vwan-sdwan, network-monitor, multi-cloud-net,
// pricing-analyst, iac-generator, container-networking, cdn-edge,
// network-automation, sase-sse, capacity-planner, ipv6-migration,
// report-builder

import { joinSession } from "@github/copilot-sdk/extension";
import { REGISTRY } from "./registry.mjs";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SPECIALISTS = join(HERE, "specialists");

// ── Update check ───────────────────────────────────────────────────────
// Lightweight, async, throttled check against the GitHub repo for a newer
// version. Runs at most once every 24h, fully non-blocking, fails silently.
// Opt out via env var NETWORK_DESK_NO_UPDATE_CHECK=1.

const UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24h
const UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/dmauser/network-desk/master/package.json";
const INSTALL_META_PATH = join(HERE, ".install-meta.json");
const UPDATE_STATE_PATH = join(HERE, ".update-check.json");

function semverGt(a, b) {
    const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
    const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
    for (let i = 0; i < 3; i++) {
        if ((pa[i] || 0) > (pb[i] || 0)) return true;
        if ((pa[i] || 0) < (pb[i] || 0)) return false;
    }
    return false;
}

async function readJsonSafe(path) {
    try { return JSON.parse(await readFile(path, "utf8")); } catch { return null; }
}

async function checkForUpdate(session) {
    if (process.env.NETWORK_DESK_NO_UPDATE_CHECK === "1") return;

    try {
        const meta = await readJsonSafe(INSTALL_META_PATH);
        const installed = meta?.version;
        if (!installed) return; // no recorded version; nothing to compare against

        const state = (await readJsonSafe(UPDATE_STATE_PATH)) || {};
        if (state.lastCheck && Date.now() - state.lastCheck < UPDATE_CHECK_INTERVAL_MS) return;

        const ac = new AbortController();
        const timer = setTimeout(() => ac.abort(), 4000);
        const res = await fetch(UPDATE_MANIFEST_URL, { signal: ac.signal, headers: { "user-agent": "network-desk-extension" } });
        clearTimeout(timer);
        if (!res.ok) return;
        const remote = await res.json();
        const latest = remote?.version;
        if (!latest) return;

        const newState = { lastCheck: Date.now(), latest, installed };
        await writeFile(UPDATE_STATE_PATH, JSON.stringify(newState, null, 2) + "\n").catch(() => {});

        if (semverGt(latest, installed)) {
            const installType = meta.installType || "user";
            const cmd = installType === "project"
                ? "npx github:dmauser/network-desk update"
                : "npx github:dmauser/network-desk update";
            await session.log(
                `network-desk: update available — installed ${installed}, latest ${latest}. ` +
                `Run \`${cmd}\` to upgrade. See CHANGELOG.md for details. ` +
                `(Disable this check with NETWORK_DESK_NO_UPDATE_CHECK=1.)`
            );
        }
    } catch {
        // never crash the extension because of an update check
    }
}

// ── File loaders ───────────────────────────────────────────────────────

// Specialist role/skill files are immutable for the lifetime of a session, so
// cache successful reads to avoid re-reading the same .md from disk on repeat
// cn_role/cn_skill calls. Failures are not cached.
const fileCache = new Map();

async function loadFile(path) {
    const cached = fileCache.get(path);
    if (cached !== undefined) return cached;
    try {
        const content = await readFile(path, "utf8");
        fileCache.set(path, content);
        return content;
    } catch (err) {
        return { textResultForLlm: `Failed to load: ${err.message}`, resultType: "failure" };
    }
}

// ── Specialist registry (single source of truth) ──────────────────────
// The REGISTRY object now lives in ./registry.mjs (dependency-free) so it can
// be shared by this runtime extension and the plugin generator
// (scripts/build-plugin.mjs). Routing, capabilities, the orchestration prompt,
// skill loading, and the generated Copilot CLI plugin are all derived from it.
// REGISTRY is imported at the top of this file.

const PREFIXES = Object.keys(REGISTRY);

// Canonical public identifier for a specialist, e.g. "vnet" -> "cn_vnet".
// REGISTRY stays keyed by the short prefix internally; the cn_ form is what
// users/the model pass as the `specialist` argument and what all output shows.
const pub = (prefix) => `cn_${prefix}`;

// ── Resolution & normalization helpers ─────────────────────────────────

// Accepts the canonical "cn_vnet" form, the bare alias "vnet", or the
// directory name "vnet-architect" (all case-insensitive). Returns the short
// REGISTRY key, or null.
function resolveSpecialist(raw) {
    if (!raw) return null;
    let key = String(raw).trim().toLowerCase();
    key = key.replace(/^cn[_-]/, ""); // strip canonical cn_ prefix if present
    if (REGISTRY[key]) return key;
    for (const [prefix, def] of Object.entries(REGISTRY)) {
        if (def.dir === key) return prefix;
    }
    return null;
}

// Accepts a skill in any of these forms and returns the canonical kebab name:
//   "address-planner", "address_planner", "vnet_skill_address_planner",
//   "skill_address_planner", "vnet-skill-address-planner", "cn_vnet_skill_address_planner"
function normalizeSkillName(prefix, raw) {
    let s = String(raw || "").trim().toLowerCase();
    s = s.replace(/^cn[_-]/, ""); // tolerate canonical "cn_<prefix>_skill_" form
    if (prefix) s = s.replace(new RegExp(`^${prefix}[_-]skill[_-]`), "");
    s = s.replace(/^[a-z0-9]+[_-]skill[_-]/, ""); // any "<prefix>_skill_" form
    s = s.replace(/^skill[_-]/, "");
    s = s.replace(/_/g, "-");
    return s;
}

// If a caller passes a legacy full name as the skill (e.g. "fw_skill_rule_audit"
// or "cn_fw_skill_rule_audit") without a specialist, infer the specialist from
// the leading prefix.
function inferSpecialistFromSkill(raw) {
    const m = String(raw || "").trim().toLowerCase()
        .replace(/^cn[_-]/, "")
        .match(/^([a-z0-9]+)[_-]skill[_-]/);
    if (m && REGISTRY[m[1]]) return m[1];
    return null;
}

// ── Output builders ────────────────────────────────────────────────────

// Friendly display name for a specialist (falls back to domain if unset).
function friendlyName(p) {
    return REGISTRY[p].name || REGISTRY[p].domain;
}

function specialistList() {
    return PREFIXES.map((p) => `| ${REGISTRY[p].icon} | ${friendlyName(p)} | \`${pub(p)}\` | ${REGISTRY[p].summary || ""} |`).join("\n");
}

let _capabilitiesSummary = null;
function buildCapabilitiesSummary() {
    if (_capabilitiesSummary !== null) return _capabilitiesSummary;
    const rows = specialistList();

    _capabilitiesSummary = `**Network Desk** is loaded and offers **${PREFIXES.length} networking specialists**, each analysis-only (no changes applied). Render the following as a Markdown table exactly as given — do not expand it into a list.

| | Specialist | Invoke as | Example use |
|---|-----------|-----------|-------------|
${rows}

Coverage spans **Azure, AWS, and GCP**, plus **14 firewall vendors** (Palo Alto, Fortinet, Check Point, Cisco, etc.).

**How to use:** describe your goal in plain language and the coordinator routes automatically. Internally: \`cn_route\` (find specialist) · \`cn_role\` (load role) · \`cn_orchestrate\` (workflow + full skill catalog for a specialist) · \`cn_skill\` (load one skill). The **Invoke as** id (e.g. \`cn_vnet\`) is passed as the \`specialist\` *argument*, not as a tool name.`;
    return _capabilitiesSummary;
}

function buildOrchestrator(prefix) {
    const def = REGISTRY[prefix];
    const skillLines = Object.entries(def.skills)
        .map(([name, desc]) => `  - \`${name}\` — ${desc}`)
        .join("\n");
    return `You are now operating as the **${def.dir}** agent — ${def.icon} ${def.domain}.

Workflow:
1. Call \`cn_role\` with { specialist: "${pub(prefix)}" } to load the full role definition (do this first).
2. For each relevant skill, call \`cn_skill\` with { specialist: "${pub(prefix)}", skill: "<name>" }.

Available skills (pass the name as the \`skill\` argument):
${skillLines}

${def.guidance}

IMPORTANT: Names such as \`${pub(prefix)}_skill_<name>\` or \`${pub(prefix)}_role\` that may appear in
documentation are references only — they are NOT callable tools. Always invoke skills via
\`cn_skill\` and the role via \`cn_role\`. End every analysis with:
"Analysis only — verify against vendor documentation before applying."`;
}

function routeQuery(query) {
    const text = String(query || "");
    const matches = PREFIXES.filter((p) => REGISTRY[p].trigger.test(text));
    if (matches.length === 0) {
        return "No specialist matched. Call `cn_capabilities` for the full map.\nAvailable specialists: " +
            PREFIXES.map((p) => `${pub(p)} (${REGISTRY[p].domain})`).join(", ");
    }
    const lines = [`Matched ${matches.length} specialist(s). Recommended call sequence:\n`];
    for (const p of matches) {
        const def = REGISTRY[p];
        const firstSkill = Object.keys(def.skills)[0];
        lines.push(`### ${def.icon} ${def.domain}`);
        lines.push("```");
        lines.push(`cn_role({ specialist: "${pub(p)}" })`);
        lines.push(`cn_orchestrate({ specialist: "${pub(p)}" })`);
        lines.push(`cn_skill({ specialist: "${pub(p)}", skill: "${firstSkill}" })   # ...and other skills as needed`);
        lines.push("```");
        lines.push("");
    }
    lines.push("Do not call legacy tool names like `" + pub(matches[0]) + "_role` directly — they are not registered tools.");
    return lines.join("\n");
}

function unknownSpecialistMsg(raw) {
    return {
        textResultForLlm:
            `Unknown specialist "${raw}". Call \`cn_skill\`/\`cn_role\`/\`cn_orchestrate\` with one of these \`specialist\` values:\n` +
            PREFIXES.map((p) => `- ${pub(p)} — ${REGISTRY[p].domain}`).join("\n"),
        resultType: "failure",
    };
}

// ── Tools (parameterized — only 5 registered, well under the 128 limit) ──

const SPECIALIST_PARAM = {
    type: "string",
    enum: PREFIXES.map(pub),
    description:
        "The specialist to engage. One of: " +
        PREFIXES.map((p) => `${pub(p)} (${REGISTRY[p].domain})`).join("; ") +
        ". Bare forms (vnet, fw, …) are also accepted as aliases.",
};

const tools = [
    {
        name: "cn_capabilities",
        description: `Returns a structured map of all ${PREFIXES.length} cloud networking specialists and their skills, plus how to invoke them via cn_role/cn_orchestrate/cn_skill. Use to discover what networking capabilities are available.`,
        parameters: { type: "object", properties: {} },
        skipPermission: true,
        handler: async () => buildCapabilitiesSummary(),
    },
    {
        name: "cn_route",
        description: "Given a cloud networking query, returns the recommended specialist(s) and the exact cn_role/cn_orchestrate/cn_skill calls to make. Use when unsure which specialist handles a request.",
        parameters: {
            type: "object",
            properties: { query: { type: "string", description: "The user's networking query or task description" } },
            required: ["query"],
        },
        skipPermission: true,
        handler: async (args) => routeQuery(args?.query),
    },
    {
        name: "cn_role",
        description: "Load a cloud networking specialist's role definition (persona, workflow, guardrails). Call this first when engaging a specialist. Select the specialist via the `specialist` argument — there are no per-specialist role tools.",
        parameters: {
            type: "object",
            properties: { specialist: SPECIALIST_PARAM },
            required: ["specialist"],
        },
        skipPermission: true,
        handler: async (args) => {
            const prefix = resolveSpecialist(args?.specialist);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            return loadFile(join(SPECIALISTS, REGISTRY[prefix].dir, "agents", `${REGISTRY[prefix].dir}.md`));
        },
    },
    {
        name: "cn_orchestrate",
        description: "Return the step-by-step orchestration workflow and skill catalog for a cloud networking specialist. Select the specialist via the `specialist` argument.",
        parameters: {
            type: "object",
            properties: { specialist: SPECIALIST_PARAM },
            required: ["specialist"],
        },
        skipPermission: true,
        handler: async (args) => {
            const prefix = resolveSpecialist(args?.specialist);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            return buildOrchestrator(prefix);
        },
    },
    {
        name: "cn_skill",
        description: "Load deep domain guidance for a specific specialist skill. Provide `specialist` (e.g. \"cn_vnet\") and `skill` (e.g. \"address-planner\"). Legacy names like \"cn_vnet_skill_address_planner\" are also accepted as the `skill` value. Call cn_capabilities or cn_orchestrate to see valid skills.",
        parameters: {
            type: "object",
            properties: {
                specialist: { ...SPECIALIST_PARAM, description: SPECIALIST_PARAM.description + " May be omitted if `skill` is a legacy full name like \"cn_vnet_skill_address_planner\"." },
                skill: { type: "string", description: "The skill name, e.g. \"address-planner\". Underscores and legacy \"<specialist>_skill_\" prefixes are tolerated." },
            },
            required: ["skill"],
        },
        skipPermission: true,
        handler: async (args) => {
            let prefix = resolveSpecialist(args?.specialist) || inferSpecialistFromSkill(args?.skill);
            if (!prefix) return unknownSpecialistMsg(args?.specialist);
            const def = REGISTRY[prefix];
            const skill = normalizeSkillName(prefix, args?.skill);
            if (!def.skills[skill]) {
                return {
                    textResultForLlm:
                        `Unknown skill "${args?.skill}" for specialist "${pub(prefix)}" (${def.domain}).\n` +
                        `Call \`cn_skill\` with one of these \`skill\` values:\n` +
                        Object.keys(def.skills).map((s) => `- ${s}`).join("\n"),
                    resultType: "failure",
                };
            }
            return loadFile(join(SPECIALISTS, def.dir, "skills", skill, "SKILL.md"));
        },
    },
];

// ── Startup registry validation (logs issues, never crashes) ───────────
// Verifies every role/skill .md referenced by the REGISTRY exists on disk.
// This is filesystem I/O that is only useful while developing the extension —
// in a published install the layout is static and already covered by CI/tests.
// It is therefore opt-in (set NETWORK_DESK_VALIDATE=1) and, when enabled,
// performs its reads concurrently rather than serially.

async function fileMissing(path) {
    try { await readFile(path, "utf8"); return false; } catch { return true; }
}

async function validateRegistry(session) {
    if (process.env.NETWORK_DESK_VALIDATE !== "1") return [];

    const problems = [];
    const seen = new Set();
    const checks = [];
    for (const [prefix, def] of Object.entries(REGISTRY)) {
        if (seen.has(prefix)) problems.push(`duplicate prefix: ${prefix}`);
        seen.add(prefix);
        try { def.trigger.test(""); } catch { problems.push(`invalid trigger regex: ${prefix}`); }
        const roleMd = join(SPECIALISTS, def.dir, "agents", `${def.dir}.md`);
        checks.push(fileMissing(roleMd).then((m) => { if (m) problems.push(`missing role md: ${def.dir}`); }));
        for (const skill of Object.keys(def.skills)) {
            const md = join(SPECIALISTS, def.dir, "skills", skill, "SKILL.md");
            checks.push(fileMissing(md).then((m) => { if (m) problems.push(`missing skill md: ${prefix}/${skill}`); }));
        }
    }
    await Promise.all(checks);
    if (problems.length) {
        await session.log(`network-desk: registry validation found ${problems.length} issue(s): ${problems.join("; ")}`);
    }
    return problems;
}

// ── Register session ───────────────────────────────────────────────────

// Matches the extension name in any form: @network-desk, network-desk,
// network desk, networkdesk (with or without a leading @).
const MENTION_RE = /(^|[^\w])@?network[\s_-]?desk\b/i;

const TOOL_USAGE_NOTE =
    "You MUST use ONLY these network-desk tools: `cn_route`, `cn_role`, `cn_orchestrate`, `cn_skill`, `cn_capabilities`. " +
    "You MUST NOT read, open, list, or search the specialist files under `specialists/**` directly with any file/view/glob/grep/shell tool. " +
    "Always load specialist content via the registered `cn_role`, `cn_orchestrate`, and `cn_skill` tools — never by reading the `.md` files yourself. " +
    "Names like `cn_vnet_role` or `vnet_skill_address_planner` are NOT registered tools; select the specialist and skill via arguments, e.g. `cn_skill({ specialist: \"cn_vnet\", skill: \"address-planner\" })`. " +
    "Respond to the user in natural language — do not list or expose internal tool names.";

// ── Hook state ─────────────────────────────────────────────────────────
// Throttle the auto-routing hint: each specialist is announced at most once
// per session so repeated matching prompts don't crowd the context window.
const announcedPrefixes = new Set();
// Presence note is injected on session start AND (belt-and-suspenders) on the
// first user prompt, so the agent learns network-desk exists before it
// decides it doesn't know about it.
let presenceAnnounced = false;

const SPECIALIST_INLINE = PREFIXES.map((p) => `${REGISTRY[p].icon} ${REGISTRY[p].domain} (${pub(p)})`).join(", ");

// Canonical on-disk layout for any artifact a specialist produces (diagrams,
// reports, generated configs). Injected into the presence note so every
// specialist saves outputs to a predictable, easy-to-navigate structure.
const OUTPUT_CONVENTION =
    "OUTPUT FILES (REQUIRED LAYOUT): When you save ANY generated artifact to disk — diagrams, reports, or generated " +
    "configs/IaC — place it under a `network-desk/` folder in the current working directory, organized by specialist " +
    "then artifact type:\n" +
    "  network-desk/<specialist>/diagrams/  — Mermaid (.mmd), Excalidraw (.excalidraw), draw.io (.drawio)\n" +
    "  network-desk/<specialist>/reports/   — .md, .html, .pdf, .docx, .xlsx\n" +
    "  network-desk/<specialist>/configs/   — generated IaC, firewall/device configs, scripts\n" +
    "`<specialist>` is the specialist's kebab-case name (e.g. vnet-architect, firewall-engineer, iac-generator, pricing-analyst). " +
    "Name files `<kebab-topic>-<YYYYMMDD>.<ext>` (e.g. `hub-spoke-3region-20260528.drawio`). Create missing subfolders. " +
    "Confirm the path with the user before writing, write only inside the working directory, and never modify live infrastructure. " +
    "To package a specialist's findings into a polished Markdown/HTML/PDF/DOCX/XLSX deliverable, use the report-builder specialist " +
    "(`cn_role({ specialist: \"cn_doc\" })` then its `report-structure` and `*-report`/`xlsx-workbook` skills).";

const PRESENCE_NOTE =
    "[network-desk] The network-desk extension (a.k.a. @network-desk) is LOADED in this session. " +
    `It bundles ${PREFIXES.length} network-desk specialists: ${SPECIALIST_INLINE}. ` +
    "Discovery tools available right now: `cn_capabilities` (full specialist + skill map), `cn_route` (pick the right specialist for a query), " +
    "`cn_role` (load a specialist's role definition — call this FIRST before answering), `cn_orchestrate` (step-by-step workflow + skill catalog), " +
    "`cn_skill` (deep guidance for a specific skill). " +
    "When the user mentions VNets/VPCs, subnets/CIDR/IP planning, firewalls/NSGs/rule audits, load balancers, DNS, Private Link/private endpoints, " +
    "hybrid connectivity (VPN/ExpressRoute/Direct Connect/Interconnect), network security, connectivity troubleshooting/packet capture, " +
    "Virtual WAN/SD-WAN, network monitoring, multi-cloud networking, networking pricing/cost, IaC (Bicep/Terraform/Ansible) for networking, " +
    "container/Kubernetes networking, CDN/edge, network automation, SASE/SSE, capacity planning, or IPv6 migration — or says 'network-desk' / " +
    "'@network-desk' / 'this extension' / 'what can you do' in a networking context — you MUST call `cn_route` (or `cn_capabilities`) FIRST, " +
    "then the matched specialist's `cn_role`, before answering. " +
    "Do NOT answer networking questions from prior/general knowledge, and do NOT read the specialist files under `specialists/**` directly — " +
    "load ALL specialist content via `cn_role` / `cn_orchestrate` / `cn_skill`. " +
    "Never claim network-desk is unavailable: it is loaded. " +
    "Network Desk is analysis-only: it never applies changes, modifies infrastructure, or runs commands against live environments. " +
    "RESPONSE FOOTER (REQUIRED): at the end of EVERY assistant response that touches cloud networking — any turn where you called a `cn_*` tool, " +
    "or discussed any networking topic above — append the following line verbatim, on its own line after all other content:\n\n" +
    "> Analysis only — verify against vendor documentation before applying.\n\n" +
    OUTPUT_CONVENTION;

const DIRECT_MENTION =
    "[network-desk — DIRECT MENTION] The user just referenced the network-desk extension by name. " +
    `It IS loaded in this session (${tools.length} tools, ${PREFIXES.length} specialists). ` +
    "Do NOT tell the user network-desk is unavailable, unknown, or not part of the CLI. " +
    "REQUIRED next action: call the `cn_capabilities` tool now to retrieve the specialist map, then answer the user's question using that information. " +
    "If the user asked for examples or how to use it, after calling `cn_capabilities` summarize the specialists and suggest 3–5 concrete example prompts " +
    "(e.g. 'design a hub-spoke VNet topology across 3 regions', 'audit my Azure Firewall rules for shadowed or overly-broad entries', " +
    "'plan a non-overlapping IP address scheme for prod/dev/test', 'troubleshoot asymmetric routing through my NVA', " +
    "'compare NAT Gateway vs egress costs across Azure/AWS/GCP', 'generate Terraform for a dual-stack hub VPC'). " +
    "Remember the response-footer rule from the presence note: end this response with " +
    "'Analysis only — verify against vendor documentation before applying.'";

const session = await joinSession({
    tools,
    hooks: {
        onSessionStart: async () => {
            // Fires on startup / new / resume — inject the presence note as
            // session-level context so the agent knows network-desk exists
            // from turn 1 without waiting for a user prompt.
            presenceAnnounced = true;
            return { additionalContext: PRESENCE_NOTE };
        },
        onUserPromptSubmitted: async (input) => {
            if (!input?.prompt) return;

            const parts = [];

            // Fallback in case onSessionStart didn't fire (older CLI builds).
            if (!presenceAnnounced) {
                presenceAnnounced = true;
                parts.push(PRESENCE_NOTE);
            }

            // Strongest signal: the user literally named the extension. Always
            // inject the imperative (not throttled) so a follow-up prompt still
            // gets the nudge if the model previously ignored it.
            const mentioned = MENTION_RE.test(input.prompt);
            if (mentioned) parts.push(DIRECT_MENTION);

            const scanText = mentioned ? input.prompt.replace(MENTION_RE, " ") : input.prompt;
            const matches = PREFIXES.filter((p) => REGISTRY[p].trigger.test(scanText));
            const fresh = matches.filter((p) => !announcedPrefixes.has(p));

            if (fresh.length > 0) {
                for (const p of fresh) announcedPrefixes.add(p);
                const guidance = fresh
                    .map((p) => `• **${REGISTRY[p].icon} ${REGISTRY[p].domain}** — \`cn_role({ specialist: "${pub(p)}" })\` then \`cn_orchestrate({ specialist: "${pub(p)}" })\``)
                    .join("\n");
                parts.push(
                    `[network-desk] Detected networking intent. The following specialist(s) MUST handle this request:\n${guidance}\n\n` +
                    `Before producing ANY substantive networking answer, you MUST call the matched specialist's role via ` +
                    `\`cn_role({ specialist })\` FIRST. Do NOT answer from prior/general knowledge, and do NOT read the ` +
                    `specialist \`.md\` files under \`specialists/**\` directly. For each specialist call \`cn_role\` then ` +
                    `\`cn_orchestrate\` (with the shown \`specialist\` value), then the relevant \`cn_skill\` calls. ` +
                    `(This routing hint is shown once per specialist per session.)\n\n` +
                    TOOL_USAGE_NOTE,
                );
            } else if (mentioned && matches.length === 0) {
                parts.push(
                    `[network-desk] No single specialist matched directly. You MUST call \`cn_route\` with the user's ` +
                    `query (or \`cn_capabilities\`) to pick the right specialist BEFORE answering — do NOT answer ` +
                    `networking questions from prior/general knowledge.\n\n` +
                    TOOL_USAGE_NOTE,
                );
            }

            if (parts.length === 0) return;
            return { additionalContext: parts.join("\n\n") };
        },
    },
});

const totalSkills = PREFIXES.reduce((n, p) => n + Object.keys(REGISTRY[p].skills).length, 0);
await session.log(
    `network-desk loaded — ${PREFIXES.length} specialists, ${totalSkills} skills, ${tools.length} tools. Trigger with @network-desk`,
);

// Validate registry against the filesystem (non-blocking).
validateRegistry(session);

// Fire-and-forget update check (throttled to once per 24h, opt-out via env var).
checkForUpdate(session);
