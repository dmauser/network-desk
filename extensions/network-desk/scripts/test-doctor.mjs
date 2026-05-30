// Standalone smoke test for cn_mcp_doctor classification.
// Run: node extensions/network-desk/scripts/test-doctor.mjs
// Exit code: 0 = all pass, 1 = any fail.

import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..");

// ESM ignores Module._resolveFilename, so we drop the SDK stub into the
// repo's node_modules just for this run, and clean it up at the end.
const STUB_ROOT = join(REPO, "node_modules", "@github", "copilot-sdk");
const STUB_OWNED = !existsSync(join(REPO, "node_modules", "@github"));
mkdirSync(STUB_ROOT, { recursive: true });
writeFileSync(
    join(STUB_ROOT, "package.json"),
    JSON.stringify({ name: "@github/copilot-sdk", version: "0.0.0", type: "module", exports: { "./extension": "./extension.mjs" } }),
);
writeFileSync(
    join(STUB_ROOT, "extension.mjs"),
    "export async function joinSession(opts) { globalThis.__NETWORK_DESK_TOOLS = opts.tools; return { log: async () => {} }; }",
);

process.env.NETWORK_DESK_NO_UPDATE_CHECK = "1";

let exitCode = 0;
try {
    const ext = await import(pathToFileURL(join(REPO, "extensions", "network-desk", "extension.mjs")).href);
    const { classifyMcpConfig, renderDoctorMarkdown } = ext;
    const tools = globalThis.__NETWORK_DESK_TOOLS || [];

let pass = 0, fail = 0;
function assert(cond, msg) {
    if (cond) { pass++; console.log("  ✅", msg); }
    else { fail++; console.log("  ❌", msg); }
}
function header(label) { console.log(`\n## ${label}`); }

const REGISTRY_KEYS = ["microsoft-learn", "azure-mcp", "aws-mcp", "gcp-mcp", "terraform-mcp", "github-mcp", "context7", "firewall-vendors"];
const TOTAL = REGISTRY_KEYS.length;

// Case 1: missing config file (config = null)
header("Case 1: missing config file");
{
    const result = classifyMcpConfig(null);
    const md = renderDoctorMarkdown(result, "file not found");
    assert(result.present.length === 0, "no present");
    assert(result.configuredNotLoaded.length === 0, "no configured-not-loaded");
    assert(result.missing.length === TOTAL, `all ${TOTAL} missing`);
    assert(result.builtins.length === 0, "no builtins reported");
    assert(/Could not read.*file not found/.test(md), "warns about missing file");
    assert(new RegExp(`Detected 0 of ${TOTAL}`).test(md), "0 of N detected line");
    assert(REGISTRY_KEYS.every((k) => md.includes("`" + k + "`")), "lists every registry key");
}

// Case 2: builtins only
header("Case 2: builtins only (filesystem + playwright)");
{
    const config = {
        servers: {
            filesystem: { builtin: true, tools: ["read_file", "write_file"] },
            playwright: { builtin: true, tools: ["browser_close"] },
        },
    };
    const result = classifyMcpConfig(config);
    const md = renderDoctorMarkdown(result, null);
    assert(result.present.length === 0, "no MCP present");
    assert(result.missing.length === TOTAL, `all ${TOTAL} missing`);
    assert(result.builtins.includes("filesystem") && result.builtins.includes("playwright"), "builtins enumerated");
    assert(/Built-in CLI servers detected.*filesystem.*playwright/s.test(md), "builtins mentioned in markdown");
}

// Case 3: azure-mcp configured but tools[] empty
header("Case 3: azure-mcp configured, tools[] empty");
{
    const config = {
        servers: {
            filesystem: { builtin: true, tools: ["read_file"] },
            "azure-mcp": { command: "npx", args: ["-y", "@azure/mcp@latest", "server", "start"], tools: [] },
        },
    };
    const result = classifyMcpConfig(config);
    const md = renderDoctorMarkdown(result, null);
    assert(result.present.length === 0, "azure-mcp not counted as present (no matching tools)");
    assert(result.configuredNotLoaded.some((c) => c.key === "azure-mcp"), "azure-mcp listed as configured-not-loaded");
    assert(result.missing.length === TOTAL - 1, `${TOTAL - 1} still missing`);
    assert(/Configured but not loaded[\s\S]*azure-mcp[\s\S]*Restart Copilot CLI/.test(md), "markdown shows azure-mcp under not-loaded with restart hint");
}

// Case 4: azure-mcp fully present (tool prefix matches)
header("Case 4: azure-mcp fully present");
{
    const config = {
        servers: {
            filesystem: { builtin: true, tools: ["read_file"] },
            "azure-mcp": { command: "npx", args: ["@azure/mcp"], tools: ["azmcp_subscription_list", "azmcp_group_list", "azmcp_kv_secret_list"] },
        },
    };
    const result = classifyMcpConfig(config);
    const md = renderDoctorMarkdown(result, null);
    assert(result.present.length === 1, "1 present");
    assert(result.present[0].key === "azure-mcp", "azure-mcp is the present one");
    assert(result.present[0].toolCount === 3, "tool count is 3");
    assert(result.configuredNotLoaded.length === 0, "nothing in not-loaded");
    assert(new RegExp(`Detected 1 of ${TOTAL}`).test(md), "1 of N detected line");
}

// Case 5 (bonus): mixed case — azure-mcp loaded, terraform-mcp configured-not-loaded, rest missing
header("Case 5: mixed (azure-mcp present, terraform-mcp configured-not-loaded)");
{
    const config = {
        servers: {
            filesystem: { builtin: true, tools: ["read_file"] },
            "azure-mcp": { command: "npx", args: ["@azure/mcp"], tools: ["azmcp_subscription_list"] },
            "terraform-mcp": { command: "docker", args: ["run", "hashicorp/terraform-mcp-server"], tools: [] },
        },
    };
    const result = classifyMcpConfig(config);
    assert(result.present.length === 1 && result.present[0].key === "azure-mcp", "only azure-mcp present");
    assert(result.configuredNotLoaded.length === 1 && result.configuredNotLoaded[0].key === "terraform-mcp", "only terraform-mcp configured-not-loaded");
    assert(result.missing.length === TOTAL - 2, `${TOTAL - 2} missing`);
}

console.log(`\n=== ${pass} passed, ${fail} failed ===`);
    exitCode = fail === 0 ? 0 : 1;

    // Case 6: cn_role output includes per-specialist MCP availability hint.
    header("Case 6: cn_role surfaces per-specialist MCP availability");
    {
        const cnRole = tools.find((t) => t.name === "cn_role");
        assert(!!cnRole, "cn_role tool registered");
        const out = await cnRole.handler({ specialist: "cn_vnet" });
        const text = typeof out === "string" ? out : (out?.textResultForLlm ?? JSON.stringify(out));
        assert(/MCP availability for/i.test(text), "role output mentions 'MCP availability for'");
        assert(/Run `cn_mcp_doctor`/.test(text), "role output nudges user to run cn_mcp_doctor");
    }
    if (fail !== 0) exitCode = 1;
    console.log(`\n=== final: ${pass} passed, ${fail} failed ===`);
} finally {
    // Clean up: only remove what we created. If the user has a real
    // node_modules tree, we leave the @github/copilot-sdk subdir alone (the
    // user can decide). When STUB_OWNED, we own the whole node_modules dir
    // and clear it.
    try {
        if (STUB_OWNED) rmSync(join(REPO, "node_modules"), { recursive: true, force: true });
        else rmSync(STUB_ROOT, { recursive: true, force: true });
    } catch {}
}
process.exit(exitCode);
