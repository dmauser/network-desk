#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────
// Network Desk — Copilot CLI plugin generator
//
// Generates a native Copilot CLI plugin (Claude Code / awesome-copilot spec)
// from the SINGLE SOURCE OF TRUTH: the REGISTRY object (extensions/network-desk
// /registry.mjs) plus the existing specialists/** role and SKILL.md files.
//
// The extension form (extension.mjs + joinSession + cn_* tools) is untouched.
// The plugin form ships ONE coordinator agent + 20 specialist skills (LLM-driven
// routing). Each specialist skill bundles its deep sub-skill SKILL.md docs under
// reference/ for on-demand (progressive) loading, preserving full depth.
//
// Output (idempotent — wiped & regenerated each run):
//   plugins/network-desk/.github/plugin/plugin.json
//   plugins/network-desk/README.md
//   plugins/network-desk/agents/network-desk.md
//   plugins/network-desk/skills/network-desk-<prefix>/SKILL.md
//   plugins/network-desk/skills/network-desk-<prefix>/reference/role.md
//   plugins/network-desk/skills/network-desk-<prefix>/reference/<skill>/...
//   .github/plugin/marketplace.json   (repo-level marketplace manifest)
//
// Usage:
//   node extensions/network-desk/scripts/build-plugin.mjs           # build
//   node extensions/network-desk/scripts/build-plugin.mjs --check   # validate sources only
// ─────────────────────────────────────────────────────────────────────────

import { REGISTRY } from "../registry.mjs";
import { readFile, writeFile, rm, mkdir, cp, rename, access } from "node:fs/promises";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const EXT_ROOT = resolve(__dirname, "..");              // extensions/network-desk
const SPECIALISTS = join(EXT_ROOT, "specialists");
const REPO_ROOT = resolve(EXT_ROOT, "..", "..");        // repo root
const PLUGIN_ID = "network-desk";
const PLUGIN_DIR = join(REPO_ROOT, "plugins", PLUGIN_ID);
const MARKETPLACE_DIR = join(REPO_ROOT, ".github", "plugin");

const GUARDRAIL = "Analysis only — verify against vendor documentation before applying.";

const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const CYAN = "\x1b[36m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";
const ok = (m) => console.log(`${GREEN}✓${RESET} ${m}`);
const err = (m) => console.log(`${RED}✗${RESET} ${m}`);
const info = (m) => console.log(`${DIM}${m}${RESET}`);

const PREFIXES = Object.keys(REGISTRY);
const skillName = (prefix) => `${PLUGIN_ID}-${prefix}`;
const OVERVIEW_SKILL = `${PLUGIN_ID}-capabilities`;

async function exists(p) {
    try { await access(p); return true; } catch { return false; }
}

// Collapse to a single line and make safe for a double-quoted YAML scalar.
function yaml1(str) {
    return String(str).replace(/\s+/g, " ").replace(/"/g, "'").trim();
}

// Pull a handful of human-readable keywords out of a routing regex source so the
// coordinator can describe each specialist's triggers without a wall of regex.
function triggerKeywords(re, limit = 10) {
    const src = re.source;
    const words = new Set();
    const re2 = /[A-Za-z][A-Za-z0-9]{2,}/g;
    const SKIP = new Set(["the", "and", "for", "with", "network", "design", "issue", "analys"]);
    let m;
    while ((m = re2.exec(src)) !== null) {
        const w = m[0];
        if (SKIP.has(w.toLowerCase())) continue;
        words.add(w);
        if (words.size >= limit) break;
    }
    return [...words].join(", ");
}

// ── Source validation (used by both build and --check) ────────────────────
async function validateSources() {
    const problems = [];
    for (const prefix of PREFIXES) {
        const spec = REGISTRY[prefix];
        const roleFile = join(SPECIALISTS, spec.dir, "agents", `${spec.dir}.md`);
        if (!(await exists(roleFile))) {
            problems.push(`[${prefix}] missing role file: ${roleFile}`);
        }
        for (const skill of Object.keys(spec.skills)) {
            const skillFile = join(SPECIALISTS, spec.dir, "skills", skill, "SKILL.md");
            if (!(await exists(skillFile))) {
                problems.push(`[${prefix}] missing skill file: ${skillFile}`);
            }
        }
    }
    return problems;
}

// ── plugin.json ───────────────────────────────────────────────────────────
function buildPluginManifest(pkg) {
    return {
        name: PLUGIN_ID,
        description: yaml1(
            "Your cloud networking AI team for GitHub Copilot CLI — one coordinator routing to " +
            `${PREFIXES.length} specialist skills across Azure, AWS, GCP and 14 firewall vendors ` +
            "(VNet/VPC design, firewall, load balancing, DNS, Private Link, hybrid, security, " +
            "troubleshooting, vWAN/SD-WAN, monitoring, multi-cloud, pricing, IaC, containers, CDN, " +
            "automation, SASE/SSE, capacity, IPv6, reporting)."
        ),
        version: pkg.version,
        author: { name: pkg.author || "dmauser" },
        homepage: "https://github.com/dmauser/network-desk",
        repository: (pkg.repository && pkg.repository.url) || "https://github.com/dmauser/network-desk",
        license: pkg.license || "MIT",
        keywords: pkg.keywords || ["copilot", "networking"],
        agents: ["./agents"],
        skills: [
            `./skills/${OVERVIEW_SKILL}`,
            ...PREFIXES.map((p) => `./skills/${skillName(p)}`),
        ],
    };
}

// ── Coordinator agent ───────────────────────────────────────────────────────
function buildCoordinatorAgent() {
    const lines = [];
    lines.push("---");
    lines.push(`description: "${yaml1(
        "Network Desk coordinator — routes any cloud networking request to the right specialist " +
        `skill (${PREFIXES.length} domains across Azure, AWS, GCP and 14 firewall vendors) and ` +
        "produces analysis-only deliverables."
    )}"`);
    lines.push(`name: "Network Desk"`);
    lines.push("---");
    lines.push("");
    lines.push("# Network Desk — Cloud Networking Coordinator");
    lines.push("");
    lines.push(
        "You are **Network Desk**, the coordinator for a team of " + PREFIXES.length +
        " cloud-networking specialists spanning Azure, AWS, GCP and 14 firewall vendor platforms. " +
        "Your job is to understand the user's networking request, route it to the matching " +
        "**specialist skill**, and deliver clear, accurate, vendor-aware guidance."
    );
    lines.push("");
    lines.push("## How to route");
    lines.push("");
    lines.push(
        "1. Identify the domain of the request from the table below (match on the *when to use* " +
        "keywords).\n" +
        "2. Load the matching specialist skill `" + skillName("<prefix>") + "` — its `SKILL.md` " +
        "indexes deeper sub-skill documents under `reference/` that you should read on demand for " +
        "the specific task.\n" +
        "3. If a request spans multiple domains, sequence the specialists (e.g., design with the " +
        "VNet skill, then price it with the pricing skill). For a polished report, do the technical " +
        "analysis with the domain specialist first, then use the **report** skill to package it.\n" +
        "4. If the request is ambiguous, ask one focused clarifying question before routing."
    );
    lines.push("");
    lines.push("## Specialist directory");
    lines.push("");
    lines.push(
        "When the user asks you to list, dump, or show your skills/specialists, render a Markdown " +
        "table with **exactly these columns** so the output stays friendly: `Specialist` (the " +
        "emoji + friendly name from the first column below), `Skill` (the `network-desk-*` id), and " +
        "`Domain`. Always keep the leading emoji and the human-readable specialist name — do not " +
        "collapse the table down to bare skill ids."
    );
    lines.push("");
    lines.push("| Specialist | Skill to load | Domain | When to use |");
    lines.push("| --- | --- | --- | --- |");
    for (const prefix of PREFIXES) {
        const s = REGISTRY[prefix];
        const kw = triggerKeywords(s.trigger);
        lines.push(
            `| ${s.icon} ${s.name} | \`${skillName(prefix)}\` | ${s.domain} | ${yaml1(kw)} |`
        );
    }
    lines.push("");
    lines.push("## Specialist scope & sub-skills");
    lines.push("");
    for (const prefix of PREFIXES) {
        const s = REGISTRY[prefix];
        lines.push(`### ${s.icon} ${s.name} — \`${skillName(prefix)}\``);
        lines.push("");
        lines.push(s.summary + ".");
        lines.push("");
        for (const [skill, desc] of Object.entries(s.skills)) {
            lines.push(`- **${skill}** — ${desc}`);
        }
        lines.push("");
    }
    lines.push("## Operating principles");
    lines.push("");
    lines.push(
        "- Cover Azure, AWS and GCP where relevant; name the cloud-specific service for each.\n" +
        "- Cite vendor documentation; prices and limits are indicative and change — flag that.\n" +
        "- You analyze, design, and generate configuration/IaC. You do **not** apply changes to " +
        "live infrastructure or run deployments.\n" +
        "- End every response with the guardrail below."
    );
    lines.push("");
    lines.push("---");
    lines.push("");
    lines.push(`*${GUARDRAIL}*`);
    lines.push("");
    return lines.join("\n");
}

// ── Capabilities overview skill ─────────────────────────────────────────────
// The plugin analogue of the extension's `cn_capabilities` tool: a single skill
// that emits the full emoji + friendly-name specialist map and example prompts,
// so "what can Network Desk do?" / "give me examples" surfaces icons reliably.
function buildOverviewSkill() {
    const desc =
        `🧭 Network Desk Capabilities — overview and index of all ${PREFIXES.length} ` +
        "cloud-networking specialists (with emoji icons) plus example prompts. Load this " +
        "whenever the user asks what Network Desk can do, its capabilities, the list of " +
        "specialists/skills, or for examples of how to use the plugin.";

    const examples = [
        "🏗️ \"Plan a /16 hub-and-spoke address space for 3 spokes with no overlap.\"",
        "🔥 \"Audit my Azure Firewall policy and migrate the rules to FortiGate.\"",
        "⚖️ \"Compare Application Gateway vs Front Door for L7 with WAF.\"",
        "🌐 \"Design a private DNS resolver setup for hybrid name resolution.\"",
        "🔗 \"Set up a Private Endpoint for Azure Storage with private DNS.\"",
        "🔐 \"Run a Zero Trust segmentation review of my NSGs against NIST.\"",
        "🛠️ \"Troubleshoot intermittent TCP resets between two VNets.\"",
        "💰 \"Estimate monthly egress + VPN cost for 5 TB cross-region traffic.\"",
        "📄 \"Turn the analysis above into a polished PDF report.\"",
    ];

    const lines = [];
    lines.push("---");
    lines.push(`name: ${OVERVIEW_SKILL}`);
    lines.push(`description: "${yaml1(desc)}"`);
    lines.push("metadata:");
    lines.push(`  displayName: "🧭 Network Desk Capabilities"`);
    lines.push(`  icon: "🧭"`);
    lines.push("---");
    lines.push("");
    lines.push("# 🧭 Network Desk — Capabilities");
    lines.push("");
    lines.push(
        "When the user asks what Network Desk can do, its capabilities, or for examples, " +
        "**reproduce the table and example prompts below verbatim, keeping every emoji icon.** " +
        "Do not drop the icons or collapse specialists down to bare `network-desk-*` ids."
    );
    lines.push("");
    lines.push(
        `**${PREFIXES.length} cloud-networking specialists** spanning Azure, AWS, GCP and 14 ` +
        "firewall vendors — analysis-only (no changes are applied)."
    );
    lines.push("");
    lines.push("| Specialist | Domain | What it does |");
    lines.push("| --- | --- | --- |");
    for (const prefix of PREFIXES) {
        const s = REGISTRY[prefix];
        lines.push(`| ${s.icon} ${s.name} | ${s.domain} | ${yaml1(s.summary || "")} |`);
    }
    lines.push("");
    lines.push("## Example prompts");
    lines.push("");
    for (const ex of examples) lines.push(`- ${ex}`);
    lines.push("");
    lines.push(
        "Just describe your goal in plain language — the **Network Desk** coordinator routes " +
        "to the right specialist automatically. For a polished deliverable, do the analysis " +
        "with a specialist first, then ask the 📄 Report Builder to package it."
    );
    lines.push("");
    lines.push("_Analysis only — verify against vendor documentation before applying._");
    lines.push("");
    return lines.join("\n");
}

// ── Specialist skill SKILL.md ───────────────────────────────────────────────
function buildSpecialistSkill(prefix) {
    const s = REGISTRY[prefix];
    const lines = [];
    const friendly = `${s.icon} ${s.name}`;
    const desc = prefix === "doc"
        ? `${friendly} — ${s.domain}. Use ONLY to package cloud-networking findings produced by ` +
          `Network Desk specialists into polished deliverables (Markdown/HTML/PDF/DOCX/XLSX). ` +
          `Do the networking analysis with a domain specialist first, then use this to render it. ` +
          `${s.summary}.`
        : `${friendly} — ${s.domain}. ${s.summary}. Use for: ${triggerKeywords(s.trigger, 14)}.`;
    lines.push("---");
    lines.push(`name: ${skillName(prefix)}`);
    lines.push(`description: "${yaml1(desc)}"`);
    lines.push("metadata:");
    lines.push(`  specialist: ${s.dir}`);
    lines.push(`  displayName: "${yaml1(`${s.icon} ${s.name}`)}"`);
    lines.push(`  icon: "${s.icon}"`);
    lines.push(`  domain: "${yaml1(s.domain)}"`);
    lines.push("---");
    lines.push("");
    lines.push(`> **${s.icon} ${s.name}** · \`${skillName(prefix)}\` · ${s.domain}`);
    lines.push("");
    lines.push(`# ${s.icon} ${s.name}`);
    lines.push("");
    lines.push(s.summary + ".");
    lines.push("");
    if (s.guidance) {
        lines.push("## Scope & guidance");
        lines.push("");
        lines.push(s.guidance);
        lines.push("");
    }
    lines.push("## Persona & workflow");
    lines.push("");
    lines.push(
        "Adopt the full role definition in [`reference/role.md`](./reference/role.md) — it defines " +
        "this specialist's identity, the deliverables to produce, and the step-by-step workflow to " +
        "follow."
    );
    lines.push("");
    lines.push("## Sub-skills (load on demand)");
    lines.push("");
    lines.push(
        "Each sub-skill below has a deep reference document under `reference/`. Read the one(s) " +
        "matching the task for detailed, vendor-specific expertise:"
    );
    lines.push("");
    for (const [skill, desc] of Object.entries(s.skills)) {
        lines.push(`- **[${skill}](./reference/${skill}/SKILL.md)** — ${desc}`);
    }
    lines.push("");
    if (prefix === "doc") {
        lines.push("## Renderer scripts (plugin form)");
        lines.push("");
        lines.push(
            "The Python renderers referenced by the sub-skills are bundled in this plugin under " +
            "`./reference/renderers/` (`make_html.py`, `make_pdf.py`, `make_docx.py`, " +
            "`make_xlsx.py`). When a sub-skill doc tells you to resolve `$RENDERERS`, use that " +
            "bundled path in plugin installs (it takes precedence over the extension-install " +
            "candidate paths listed in the sub-skill docs)."
        );
        lines.push("");
    }
    lines.push("---");
    lines.push("");
    lines.push(`*${GUARDRAIL}*`);
    lines.push("");
    return lines.join("\n");
}

// ── Plugin README ───────────────────────────────────────────────────────────
function buildPluginReadme(pkg) {
    const lines = [];
    lines.push("# Network Desk — Copilot CLI Plugin");
    lines.push("");
    lines.push(
        "Your cloud networking AI team, packaged as a **native GitHub Copilot CLI plugin**. " +
        "One coordinator agent (`Network Desk`) routes your request to one of " + PREFIXES.length +
        " specialist skills across Azure, AWS, GCP and 14 firewall vendor platforms."
    );
    lines.push("");
    lines.push("> Generated from the Network Desk single source of truth. Do not edit by hand —");
    lines.push("> run `node extensions/network-desk/scripts/build-plugin.mjs` to regenerate.");
    lines.push("");
    lines.push("## Install");
    lines.push("");
    lines.push("Directly from the repository (no marketplace needed):");
    lines.push("");
    lines.push("```sh");
    lines.push(`copilot plugin install dmauser/network-desk:plugins/${PLUGIN_ID}`);
    lines.push("```");
    lines.push("");
    lines.push("Or register the repo as a marketplace, then install by name:");
    lines.push("");
    lines.push("```sh");
    lines.push("copilot plugin marketplace add dmauser/network-desk");
    lines.push(`copilot plugin install ${PLUGIN_ID}@network-desk`);
    lines.push("```");
    lines.push("");
    lines.push("## Specialists");
    lines.push("");
    lines.push("| Specialist | Skill | Domain |");
    lines.push("| --- | --- | --- |");
    for (const prefix of PREFIXES) {
        const s = REGISTRY[prefix];
        lines.push(`| ${s.icon} ${s.name} | \`${skillName(prefix)}\` | ${s.domain} |`);
    }
    lines.push("");
    lines.push("## Extension vs. plugin");
    lines.push("");
    lines.push(
        "This plugin is an **alternative** to the Network Desk SDK extension. The extension form " +
        "(installed via `network-desk init`) keeps deterministic regex-based routing and the " +
        "parameterized `cn_*` tools. The plugin form uses **LLM-driven routing** through the " +
        "coordinator agent — simpler to install, slightly less deterministic. Both are generated " +
        "from the same source and deliver the same specialist depth."
    );
    lines.push("");
    lines.push("---");
    lines.push("");
    lines.push(`*${GUARDRAIL}*`);
    lines.push("");
    return lines.join("\n");
}

// ── marketplace.json ────────────────────────────────────────────────────────
function buildMarketplace(pkg) {
    return {
        name: "network-desk",
        owner: { name: pkg.author || "dmauser" },
        metadata: {
            description: "Network Desk — cloud networking specialist plugin(s) for Copilot CLI.",
            version: pkg.version,
        },
        plugins: [
            {
                name: PLUGIN_ID,
                description: yaml1(pkg.description || "Cloud networking AI team."),
                version: pkg.version,
                source: `plugins/${PLUGIN_ID}`,
            },
        ],
    };
}

// ── Output validation ───────────────────────────────────────────────────────
async function validateOutput(baseDir, manifest) {
    const problems = [];
    if (!(await exists(join(baseDir, "agents", "network-desk.md")))) {
        problems.push("missing coordinator agent agents/network-desk.md");
    }
    for (const rel of manifest.skills) {
        const skillMd = join(baseDir, rel.replace(/^\.\//, ""), "SKILL.md");
        if (!(await exists(skillMd))) {
            problems.push(`missing emitted skill: ${skillMd}`);
            continue;
        }
        const body = await readFile(skillMd, "utf8");
        if (!body.startsWith("---\n") || !/\nname:\s*\S+/.test(body)) {
            problems.push(`skill missing YAML frontmatter/name: ${skillMd}`);
        }
    }
    return problems;
}

// ── Build ───────────────────────────────────────────────────────────────────

// Move `from` -> `to`, tolerating Windows/OneDrive EPERM/EBUSY on rename by
// retrying briefly and then falling back to a recursive copy.
async function swapIntoPlace(from, to) {
    const delays = [50, 150, 300, 600, 1000];
    for (let i = 0; i <= delays.length; i++) {
        try {
            await rename(from, to);
            return;
        } catch (err) {
            const retryable = err && (err.code === "EPERM" || err.code === "EBUSY" || err.code === "ENOTEMPTY");
            if (!retryable || i === delays.length) {
                if (!retryable) throw err;
                // Final fallback: copy the tree, then remove staging.
                await cp(from, to, { recursive: true });
                await rm(from, { recursive: true, force: true });
                return;
            }
            await new Promise((r) => setTimeout(r, delays[i]));
        }
    }
}

async function build() {
    console.log("");
    console.log(`${CYAN}Network Desk${RESET} — generating Copilot CLI plugin`);
    console.log("");

    const srcProblems = await validateSources();
    if (srcProblems.length) {
        srcProblems.forEach(err);
        throw new Error(`Source validation failed (${srcProblems.length} problem(s)).`);
    }
    ok(`Source validation passed (${PREFIXES.length} specialists)`);

    const pkg = JSON.parse(await readFile(join(REPO_ROOT, "package.json"), "utf8"));

    // Build into a staging directory, validate it, then atomically swap it in.
    // This avoids leaving a half-written/broken bundle if generation fails.
    const STAGE = PLUGIN_DIR + ".staging";
    await rm(STAGE, { recursive: true, force: true });
    await mkdir(join(STAGE, ".github", "plugin"), { recursive: true });
    await mkdir(join(STAGE, "agents"), { recursive: true });
    await mkdir(join(STAGE, "skills"), { recursive: true });

    // plugin.json
    const manifest = buildPluginManifest(pkg);
    await writeFile(
        join(STAGE, ".github", "plugin", "plugin.json"),
        JSON.stringify(manifest, null, 2) + "\n"
    );

    // Coordinator agent
    await writeFile(join(STAGE, "agents", "network-desk.md"), buildCoordinatorAgent());

    // Capabilities overview skill (emoji + friendly-name map; no reference docs)
    const overviewDir = join(STAGE, "skills", OVERVIEW_SKILL);
    await mkdir(overviewDir, { recursive: true });
    await writeFile(join(overviewDir, "SKILL.md"), buildOverviewSkill());

    // Specialist skills
    let copiedRefs = 0;
    for (const prefix of PREFIXES) {
        const s = REGISTRY[prefix];
        const skillDir = join(STAGE, "skills", skillName(prefix));
        const refDir = join(skillDir, "reference");
        await mkdir(refDir, { recursive: true });

        await writeFile(join(skillDir, "SKILL.md"), buildSpecialistSkill(prefix));

        // Bundle the full role definition as reference/role.md
        await cp(
            join(SPECIALISTS, s.dir, "agents", `${s.dir}.md`),
            join(refDir, "role.md")
        );
        copiedRefs++;

        // Bundle each sub-skill folder (SKILL.md + any assets) under reference/<skill>/
        for (const skill of Object.keys(s.skills)) {
            await cp(
                join(SPECIALISTS, s.dir, "skills", skill),
                join(refDir, skill),
                { recursive: true }
            );
            copiedRefs++;
        }

        // The report-builder skills invoke Python renderers that live at the
        // extension root; bundle them so the skill works in plugin installs too.
        if (prefix === "doc") {
            const renderersSrc = join(EXT_ROOT, "renderers");
            if (await exists(renderersSrc)) {
                await cp(renderersSrc, join(refDir, "renderers"), { recursive: true });
                copiedRefs++;
            } else {
                throw new Error("report-builder ('doc') requires renderers/, but it was not found.");
            }
        }
    }
    ok(`Emitted coordinator + ${PREFIXES.length} specialist skills (${copiedRefs} reference docs bundled)`);

    // Plugin README
    await writeFile(join(STAGE, "README.md"), buildPluginReadme(pkg));

    // Validate the staged bundle before swapping it in.
    const outProblems = await validateOutput(STAGE, manifest);
    if (outProblems.length) {
        outProblems.forEach(err);
        await rm(STAGE, { recursive: true, force: true });
        throw new Error(`Output validation failed (${outProblems.length} problem(s)).`);
    }
    ok("Output validation passed");

    // Atomic-ish swap: remove old bundle, move staging into place.
    await rm(PLUGIN_DIR, { recursive: true, force: true });
    await swapIntoPlace(STAGE, PLUGIN_DIR);

    // Repo-level marketplace manifest (written after the bundle is in place).
    await mkdir(MARKETPLACE_DIR, { recursive: true });
    await writeFile(
        join(MARKETPLACE_DIR, "marketplace.json"),
        JSON.stringify(buildMarketplace(pkg), null, 2) + "\n"
    );
    ok("Wrote .github/plugin/marketplace.json");

    console.log("");
    info(`Plugin written to plugins/${PLUGIN_ID}/`);
    info(`Install:  copilot plugin marketplace add dmauser/network-desk && copilot plugin install ${PLUGIN_ID}@network-desk`);
    console.log("");
}

// ── Entry ─────────────────────────────────────────────────────────────────
const checkOnly = process.argv.includes("--check");
try {
    if (checkOnly) {
        const problems = await validateSources();
        if (problems.length) {
            problems.forEach(err);
            err(`Source validation failed (${problems.length} problem(s)).`);
            process.exit(1);
        }
        ok(`Source validation passed (${PREFIXES.length} specialists, ` +
            `${PREFIXES.reduce((n, p) => n + Object.keys(REGISTRY[p].skills).length, 0)} sub-skills)`);
    } else {
        await build();
    }
} catch (e) {
    err(e.message);
    process.exit(1);
}
