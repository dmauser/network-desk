import { pathToFileURL, fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const EXT_DIR = join(REPO_ROOT, "extensions", "network-desk");

let counter = 0;

// Load a fresh copy of extension.mjs (fresh per-session state) and return the
// captured joinSession config. Requires the SDK stub loader (register-stub.mjs).
export async function loadExtension() {
    process.env.NETWORK_DESK_NO_UPDATE_CHECK = "1";
    const url = pathToFileURL(join(EXT_DIR, "extension.mjs")).href + `?fresh=${++counter}`;
    await import(url);
    const captured = globalThis.__networkDeskSession;
    if (!captured) throw new Error("extension did not call joinSession");
    const tools = Object.fromEntries(captured.config.tools.map((t) => [t.name, t]));
    return { config: captured.config, tools, hooks: captured.config.hooks, logs: captured.logs };
}

// Tool handlers may return a string or { textResultForLlm, ... }; normalize.
export function text(result) {
    if (typeof result === "string") return result;
    if (result && typeof result.textResultForLlm === "string") return result.textResultForLlm;
    return JSON.stringify(result);
}
