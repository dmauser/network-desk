// Run cn_mcp_doctor against the real local config and print the markdown.
import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..");
const STUB_ROOT = join(REPO, "node_modules", "@github", "copilot-sdk");
const STUB_OWNED = !existsSync(join(REPO, "node_modules", "@github"));
mkdirSync(STUB_ROOT, { recursive: true });
writeFileSync(join(STUB_ROOT, "package.json"), JSON.stringify({ name: "@github/copilot-sdk", version: "0.0.0", type: "module", exports: { "./extension": "./extension.mjs" } }));
writeFileSync(join(STUB_ROOT, "extension.mjs"), "export async function joinSession(opts) { globalThis.__NETWORK_DESK_TOOLS = opts.tools; return { log: async () => {} }; }");
process.env.NETWORK_DESK_NO_UPDATE_CHECK = "1";
try {
    const ext = await import(pathToFileURL(join(REPO, "extensions", "network-desk", "extension.mjs")).href);
    // Find the cn_mcp_doctor tool and invoke it.
    const tools = globalThis.__NETWORK_DESK_TOOLS || [];
    const doctor = tools.find((t) => t.name === "cn_mcp_doctor");
    if (!doctor) { console.error("cn_mcp_doctor not registered"); process.exit(2); }
    const out = await doctor.handler({});
    const text = typeof out === "string" ? out : (out?.content?.[0]?.text ?? JSON.stringify(out));
    console.log(text);
} finally {
    try { if (STUB_OWNED) rmSync(join(REPO, "node_modules"), { recursive: true, force: true }); else rmSync(STUB_ROOT, { recursive: true, force: true }); } catch {}
}
