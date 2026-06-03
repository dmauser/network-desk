#!/usr/bin/env node

import { cp, rm, mkdir, access, readdir, readFile, appendFile, writeFile } from "node:fs/promises";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { execSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(__dirname, "..");
const EXTENSION_SRC = join(PKG_ROOT, "extensions", "network-desk");
const COPILOT_DIR = join(homedir(), ".copilot");
const EXT_DEST = join(COPILOT_DIR, "extensions", "network-desk");

// Native Copilot CLI plugin bundle (generated from the same single source of
// truth as the extension). Shipped prebuilt in the npm package.
const PLUGIN_ID = "network-desk";
const PLUGIN_BUNDLE = join(PKG_ROOT, "plugins", PLUGIN_ID);
const PLUGIN_GENERATOR = join(EXTENSION_SRC, "scripts", "build-plugin.mjs");
const MARKETPLACE_MANIFEST = join(PKG_ROOT, ".github", "plugin", "marketplace.json");
const PLUGIN_MARKET_SPEC = "network-desk@network-desk";

const GITIGNORE_ENTRY = ".github/extensions/network-desk/";

// Legacy bundle directory names that registered the same cn_* tools and would
// conflict if left installed alongside network-desk (e.g. before the rename).
const LEGACY_BUNDLE_NAMES = ["cloud-networking"];

const SPECIALIST_NAMES = [
    "vnet-architect", "firewall-engineer", "load-balancer",
    "dns-specialist", "private-link", "hybrid-connectivity",
    "network-security", "network-troubleshooter", "vwan-sdwan",
    "network-monitor", "multi-cloud-net", "pricing-analyst",
];

const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

const log = (msg) => console.log(msg);
const ok = (msg) => log(`${GREEN}✓${RESET} ${msg}`);
const err = (msg) => log(`${RED}✗${RESET} ${msg}`);
const info = (msg) => log(`${DIM}${msg}${RESET}`);

async function exists(path) {
    try { await access(path); return true; } catch { return false; }
}

async function writeInstallMeta(destDir, installType) {
    try {
        const pkgPath = join(PKG_ROOT, "package.json");
        const pkg = JSON.parse(await readFile(pkgPath, "utf8"));
        const meta = {
            version: pkg.version,
            installType,
            installedAt: new Date().toISOString(),
            source: "github:dmauser/network-desk",
        };
        await writeFile(join(destDir, ".install-meta.json"), JSON.stringify(meta, null, 2) + "\n");
    } catch {
        // best-effort; install must not fail because of metadata
    }
}

async function readInstallMeta(destDir) {
    try {
        return JSON.parse(await readFile(join(destDir, ".install-meta.json"), "utf8"));
    } catch {
        return null;
    }
}

// ── Commands ──────────────────────────────────────────────────────────

function findGitRoot() {
    try {
        return execSync("git rev-parse --show-toplevel", { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }).trim();
    } catch {
        return null;
    }
}

async function addToGitignore(repoRoot) {
    const gitignorePath = join(repoRoot, ".gitignore");
    try {
        const content = await readFile(gitignorePath, "utf8");
        if (content.includes(GITIGNORE_ENTRY)) return;
        const separator = content.endsWith("\n") ? "" : "\n";
        await appendFile(gitignorePath, `${separator}\n# Network Desk extension (installed per-developer)\n${GITIGNORE_ENTRY}\n`);
    } catch {
        await writeFile(gitignorePath, `# Network Desk extension (installed per-developer)\n${GITIGNORE_ENTRY}\n`);
    }
    ok(`Added ${GITIGNORE_ENTRY} to .gitignore`);
}

async function initProject() {
    log("");
    log(`${CYAN}Network Desk${RESET} — installing extensions (project-level)`);
    log("");

    const repoRoot = findGitRoot();
    const projectRoot = repoRoot || process.cwd();

    if (!repoRoot) {
        info("Not inside a git repository — initializing one...");
        execSync("git init", { cwd: projectRoot, stdio: "ignore" });
        ok(`Initialized git repository in ${projectRoot}`);
    }

    const projectDest = join(projectRoot, ".github", "extensions", "network-desk");

    // Remove legacy bundle installs (renamed) that register the same cn_* tools
    for (const name of LEGACY_BUNDLE_NAMES) {
        const legacyDest = join(projectRoot, ".github", "extensions", name);
        if (await exists(legacyDest)) {
            await rm(legacyDest, { recursive: true, force: true });
            ok(`Removed legacy '${name}' extension (renamed to network-desk)`);
        }
    }

    if (await exists(projectDest)) {
        info("Existing project-level installation found — replacing...");
        await rm(projectDest, { recursive: true, force: true });
    }

    await mkdir(join(projectRoot, ".github", "extensions"), { recursive: true });
    await cp(EXTENSION_SRC, projectDest, { recursive: true });
    await writeInstallMeta(projectDest, "project");
    ok("Extension installed to .github/extensions/network-desk/");

    await addToGitignore(projectRoot);

    const specialistsDir = join(projectDest, "specialists");
    if (await exists(specialistsDir)) {
        const specialists = (await readdir(specialistsDir, { withFileTypes: true }))
            .filter(d => d.isDirectory())
            .map(d => d.name);
        ok(`${specialists.length} specialists loaded: ${specialists.join(", ")}`);
    }

    log("");
    log("Get started:");
    log("");
    log(`  ${DIM}# Launch Copilot from this repo (no experimental mode needed):${RESET}`);
    log(`  copilot`);
    log("");
    log(`  ${DIM}# The extension loads automatically from .github/extensions/${RESET}`);
    log("");
}

async function init() {
    log("");
    log(`${CYAN}Network Desk${RESET} — installing extensions`);
    log("");

    const extDir = join(COPILOT_DIR, "extensions");
    await mkdir(extDir, { recursive: true });

    // Remove individual specialist extensions that conflict with the bundle
    let removed = 0;
    for (const name of SPECIALIST_NAMES) {
        const p = join(extDir, name);
        if (await exists(p)) {
            await rm(p, { recursive: true, force: true });
            removed++;
        }
    }
    if (removed > 0) {
        ok(`Removed ${removed} individual specialist extension(s) (replaced by bundle)`);
    }

    // Remove legacy bundle installs (renamed) that register the same cn_* tools
    for (const name of LEGACY_BUNDLE_NAMES) {
        const p = join(extDir, name);
        if (await exists(p)) {
            await rm(p, { recursive: true, force: true });
            ok(`Removed legacy '${name}' extension (renamed to network-desk)`);
        }
    }

    if (await exists(EXT_DEST)) {
        info("Existing installation found — replacing...");
        await rm(EXT_DEST, { recursive: true, force: true });
    }

    await cp(EXTENSION_SRC, EXT_DEST, { recursive: true });
    await writeInstallMeta(EXT_DEST, "user");
    ok("Extension installed to ~/.copilot/extensions/network-desk/");

    const specialistsDir = join(EXT_DEST, "specialists");
    if (await exists(specialistsDir)) {
        const specialists = (await readdir(specialistsDir, { withFileTypes: true }))
            .filter(d => d.isDirectory())
            .map(d => d.name);
        ok(`${specialists.length} specialists loaded: ${specialists.join(", ")}`);
    }

    log("");
    log("Get started:");
    log("");
    log(`  ${DIM}# Launch Copilot with experimental mode (required for user-level extensions):${RESET}`);
    log(`  copilot --experimental`);
    log("");
    log(`  ${DIM}# Or install per-project instead (no experimental mode needed):${RESET}`);
    log(`  network-desk init --project`);
    log("");
}

async function uninstall() {
    const isProject = process.argv.includes("--project");

    log("");
    log(`${CYAN}Network Desk${RESET} — uninstalling${isProject ? " (project-level)" : ""}`);
    log("");

    if (isProject) {
        const repoRoot = findGitRoot();
        if (!repoRoot) {
            err("Not inside a git repository.");
            process.exit(1);
        }
        const projectDest = join(repoRoot, ".github", "extensions", "network-desk");
        if (await exists(projectDest)) {
            await rm(projectDest, { recursive: true, force: true });
            ok("Removed .github/extensions/network-desk/");
        } else {
            info("No project-level installation found.");
        }
    } else {
        if (await exists(EXT_DEST)) {
            await rm(EXT_DEST, { recursive: true, force: true });
            ok("Removed ~/.copilot/extensions/network-desk/");
        } else {
            info("Not installed — nothing to remove.");
        }

        const extDir = join(COPILOT_DIR, "extensions");
        for (const name of SPECIALIST_NAMES) {
            const p = join(extDir, name);
            if (await exists(p)) {
                await rm(p, { recursive: true, force: true });
                ok(`Removed leftover: ${name}`);
            }
        }
    }
    log("");
}

async function status() {
    log("");
    log(`${CYAN}Network Desk${RESET} — status`);
    log("");

    let found = false;

    if (await exists(EXT_DEST)) {
        found = true;
        ok("User-level: installed at ~/.copilot/extensions/network-desk/");
        info("  Requires: copilot --experimental");

        const meta = await readInstallMeta(EXT_DEST);
        if (meta) {
            info(`  Installed version: ${meta.version} (${meta.installedAt})`);
        }

        const specialistsDir = join(EXT_DEST, "specialists");
        if (await exists(specialistsDir)) {
            const specialists = (await readdir(specialistsDir, { withFileTypes: true }))
                .filter(d => d.isDirectory());
            ok(`  ${specialists.length} specialists available`);
            for (const s of specialists) {
                info(`    • ${s.name}`);
            }
        }

        const extDir = join(COPILOT_DIR, "extensions");
        const conflicts = [];
        for (const name of SPECIALIST_NAMES) {
            if (await exists(join(extDir, name))) conflicts.push(name);
        }
        if (conflicts.length > 0) {
            err(`  ${conflicts.length} conflicting individual extension(s) found — run 'network-desk init' to fix`);
        }
    }

    const repoRoot = findGitRoot();
    if (repoRoot) {
        const projectDest = join(repoRoot, ".github", "extensions", "network-desk");
        if (await exists(projectDest)) {
            found = true;
            ok(`Project-level: installed at .github/extensions/network-desk/`);
            info("  Works without experimental mode");

            const projMeta = await readInstallMeta(projectDest);
            if (projMeta) {
                info(`  Installed version: ${projMeta.version} (${projMeta.installedAt})`);
            }

            const specialistsDir = join(projectDest, "specialists");
            if (await exists(specialistsDir)) {
                const specialists = (await readdir(specialistsDir, { withFileTypes: true }))
                    .filter(d => d.isDirectory());
                ok(`  ${specialists.length} specialists available`);
            }
        }
    }

    if (!found) {
        err("Not installed. Run: network-desk init");
        info("  User-level:    network-desk init");
        info("  Project-level: network-desk init --project");
    }

    // Plugin bundle awareness (the native Copilot CLI plugin form).
    log("");
    if (await exists(join(PLUGIN_BUNDLE, ".github", "plugin", "plugin.json"))) {
        ok("Plugin bundle: present at plugins/network-desk/");
        if (copilotAvailable()) {
            info("  Check if installed: copilot plugin list");
        } else {
            info("  Install with: network-desk init --plugin");
        }
    } else {
        info("Plugin bundle: not built (run 'network-desk plugin build')");
    }
    log("");
}

async function update() {
    log("");
    log(`${CYAN}Network Desk${RESET} — checking for installations to update`);
    log("");

    let updated = false;

    if (await exists(EXT_DEST)) {
        info("User-level installation detected — updating...");
        log("");
        await init();
        updated = true;
    }

    const repoRoot = findGitRoot();
    if (repoRoot) {
        const projectDest = join(repoRoot, ".github", "extensions", "network-desk");
        if (await exists(projectDest)) {
            info("Project-level installation detected — updating...");
            log("");
            await initProject();
            updated = true;
        }
    }

    // Plugin form: if the Copilot CLI plugin is installed, rebuild the bundle and
    // refresh it via `copilot plugin update`.
    if (copilotAvailable() && pluginInstalled()) {
        info("Copilot CLI plugin detected — rebuilding bundle and updating...");
        log("");
        if (await exists(PLUGIN_GENERATOR)) {
            try { execSync(`node "${PLUGIN_GENERATOR}"`, { stdio: "inherit", cwd: PKG_ROOT }); } catch {}
        }
        try {
            execSync(`copilot plugin update ${PLUGIN_ID}`, { stdio: "inherit" });
            ok("Plugin updated.");
        } catch {
            err(`Could not update the plugin automatically — run: copilot plugin update ${PLUGIN_ID}`);
        }
        log("");
        updated = true;
    }

    if (!updated) {
        err("Nothing to update — extension is not installed.");
        info("  User-level:    network-desk init");
        info("  Project-level: network-desk init --project");
        log("");
    }
}

// ── Plugin (native Copilot CLI plugin) commands ───────────────────────

function copilotAvailable() {
    try {
        execSync("copilot --version", { stdio: "ignore" });
        return true;
    } catch {
        return false;
    }
}

function pluginInstalled() {
    try {
        const out = execSync("copilot plugin list", { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] });
        return /(^|\s)network-desk(\s|@|$)/m.test(out);
    } catch {
        return false;
    }
}

async function pluginBuild() {
    log("");
    log(`${CYAN}Network Desk${RESET} — building Copilot CLI plugin bundle`);
    log("");
    if (!await exists(PLUGIN_GENERATOR)) {
        err(`Generator not found: ${PLUGIN_GENERATOR}`);
        process.exit(1);
    }
    try {
        execSync(`node "${PLUGIN_GENERATOR}"`, { stdio: "inherit", cwd: PKG_ROOT });
    } catch {
        err("Plugin generation failed.");
        process.exit(1);
    }
}

async function initPlugin() {
    log("");
    log(`${CYAN}Network Desk${RESET} — installing as a Copilot CLI plugin`);
    log("");

    // Ensure the bundle exists; build it from source if missing.
    if (!await exists(join(PLUGIN_BUNDLE, ".github", "plugin", "plugin.json"))) {
        info("Plugin bundle not found — generating it...");
        if (!await exists(PLUGIN_GENERATOR)) {
            err("Cannot build: plugin generator is missing from this package.");
            process.exit(1);
        }
        execSync(`node "${PLUGIN_GENERATOR}"`, { stdio: "inherit", cwd: PKG_ROOT });
        log("");
    }

    if (!copilotAvailable()) {
        info("Copilot CLI ('copilot') not found on PATH.");
        printPluginInstallSteps();
        log("");
        return;
    }

    // Preferred: register the local marketplace and install by name (the direct
    // path/repo install forms are deprecated in newer Copilot CLI releases).
    const haveMarketplace = await exists(MARKETPLACE_MANIFEST);
    if (haveMarketplace) {
        info("Copilot CLI detected — registering the local marketplace...");
        try {
            execSync(`copilot plugin marketplace add "${PKG_ROOT}"`, { stdio: "inherit" });
        } catch {
            // Most likely already registered — continue to install.
        }
        try {
            execSync(`copilot plugin install ${PLUGIN_MARKET_SPEC}`, { stdio: "inherit" });
            log("");
            ok("Plugin installed.");
            info("  Verify with: copilot plugin list");
            info("  The 'Network Desk' coordinator agent routes to 20 specialist skills.");
            log("");
            return;
        } catch {
            // Install can fail simply because it's already installed — treat that
            // as success; otherwise fall back to a direct install.
            if (pluginInstalled()) {
                log("");
                ok("Plugin already installed (run 'network-desk update' to refresh it).");
                log("");
                return;
            }
            info("Marketplace install failed — falling back to a direct local install...");
        }
    }

    // Fallback: direct local-path install.
    try {
        execSync(`copilot plugin install "${PLUGIN_BUNDLE}"`, { stdio: "inherit" });
        log("");
        ok("Plugin installed.");
        info("  Verify with: copilot plugin list");
    } catch {
        if (pluginInstalled()) {
            log("");
            ok("Plugin already installed.");
        } else {
            err("`copilot plugin install` failed — install manually with the steps below.");
            printPluginInstallSteps();
        }
    }
    log("");
}

function printPluginInstallSteps() {
    log("");
    log("Install the plugin with any of:");
    log("");
    log(`  ${DIM}# Recommended — register the local marketplace, then install by name:${RESET}`);
    log(`  copilot plugin marketplace add "${PKG_ROOT}"`);
    log(`  copilot plugin install ${PLUGIN_MARKET_SPEC}`);
    log("");
    log(`  ${DIM}# Or directly from GitHub once published:${RESET}`);
    log(`  copilot plugin marketplace add dmauser/network-desk`);
    log(`  copilot plugin install ${PLUGIN_MARKET_SPEC}`);
    log("");
    log(`  ${DIM}# Or a direct local-path install (deprecated in newer CLI releases):${RESET}`);
    log(`  copilot plugin install "${PLUGIN_BUNDLE}"`);
}

async function uninstallPlugin() {
    log("");
    log(`${CYAN}Network Desk${RESET} — uninstalling plugin`);
    log("");
    if (copilotAvailable()) {
        try {
            execSync(`copilot plugin uninstall ${PLUGIN_ID}`, { stdio: "inherit" });
            ok("Plugin uninstalled.");
        } catch {
            err(`Could not uninstall — run: copilot plugin uninstall ${PLUGIN_ID}`);
        }
    } else {
        info("Copilot CLI not found on PATH.");
        info(`  Run manually: copilot plugin uninstall ${PLUGIN_ID}`);
    }
    log("");
}

async function showVersion() {
    try {
        const pkg = JSON.parse(await readFile(join(PKG_ROOT, "package.json"), "utf8"));
        log(pkg.version);
    } catch {
        log("unknown");
    }
}

function showHelp() {
    log("");
    log(`${CYAN}Network Desk${RESET} — your cloud networking AI team`);
    log("");
    log("Usage: network-desk <command> [options]");
    log("");
    log("Commands:");
    log("  init              Install extensions to ~/.copilot/extensions/ (requires experimental mode)");
    log("  init --project    Install extensions to .github/extensions/ in current repo (no experimental mode needed)");
    log("  init --plugin     Install as a native Copilot CLI plugin (copilot plugin install)");
    log("  plugin build      (Re)generate the plugin bundle from the registry source");
    log("  update            Re-install over any existing user-level and/or project-level install (pulls latest)");
    log("  uninstall         Remove user-level extensions");
    log("  uninstall --project  Remove project-level extensions from current repo");
    log("  uninstall --plugin   Remove the installed Copilot CLI plugin");
    log("  status            Check installation status (extensions + plugin bundle)");
    log("  --version, -v     Print the installed CLI version");
    log("  help              Show this help");
    log("");
}

// ── Main ──────────────────────────────────────────────────────────────

const command = process.argv[2];
const flags = process.argv.slice(3);
const isProject = flags.includes("--project");
const isPlugin = flags.includes("--plugin");

switch (command) {
    case "init":
        if (isPlugin) {
            await initPlugin();
        } else if (isProject) {
            await initProject();
        } else {
            await init();
        }
        break;
    case "plugin":
        if (flags[0] === "build" || process.argv[3] === "build") {
            await pluginBuild();
        } else {
            err("Usage: network-desk plugin build");
            process.exit(1);
        }
        break;
    case "update":
    case "upgrade":
        await update();
        break;
    case "uninstall":
    case "remove":
        if (isPlugin) {
            await uninstallPlugin();
        } else {
            await uninstall();
        }
        break;
    case "status":
        await status();
        break;
    case "--version":
    case "-v":
    case "version":
        await showVersion();
        break;
    case "help":
    case "--help":
    case "-h":
    case undefined:
        showHelp();
        break;
    default:
        err(`Unknown command: ${command}`);
        showHelp();
        process.exit(1);
}
