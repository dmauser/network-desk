// Drift check: regenerating the Copilot CLI plugin from REGISTRY + specialists
// must reproduce the committed plugins/network-desk/** and marketplace.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { REPO_ROOT, EXT_DIR } from "./harness.mjs";

const norm = (b) => b.toString("utf8").replace(/\r\n/g, "\n");

async function walk(dir) {
    const out = [];
    for (const e of await readdir(dir, { withFileTypes: true })) {
        const p = join(dir, e.name);
        if (e.isDirectory()) out.push(...(await walk(p)));
        else out.push(p);
    }
    return out;
}

test("generated network-desk plugin matches committed bundle", async () => {
    const tmp = await mkdtemp(join(tmpdir(), "nd-build-"));
    try {
        execFileSync(process.execPath, [join(EXT_DIR, "scripts", "build-plugin.mjs"), "--out", tmp], { stdio: "pipe" });
        const genRoot = join(tmp, "plugins", "network-desk");
        const repoRoot = join(REPO_ROOT, "plugins", "network-desk");
        const gen = (await walk(genRoot)).map((p) => relative(genRoot, p)).sort();
        const committed = (await walk(repoRoot)).map((p) => relative(repoRoot, p)).sort();
        assert.deepEqual(gen, committed, "file list drift — run `node bin/cli.mjs plugin build`");
        for (const rel of gen) {
            assert.equal(
                norm(await readFile(join(genRoot, rel))),
                norm(await readFile(join(repoRoot, rel))),
                `content drift in plugins/network-desk/${rel} — run \`node bin/cli.mjs plugin build\``,
            );
        }
        assert.equal(
            norm(await readFile(join(tmp, ".github", "plugin", "marketplace.json"))),
            norm(await readFile(join(REPO_ROOT, ".github", "plugin", "marketplace.json"))),
            "marketplace.json drift",
        );
    } finally {
        await rm(tmp, { recursive: true, force: true });
    }
});

test("plugin manifest declares skills in SRE Agent object form", async () => {
    const manifest = JSON.parse(
        await readFile(join(REPO_ROOT, "plugins", "network-desk", ".github", "plugin", "plugin.json"), "utf8"),
    );
    for (const s of manifest.skills) {
        assert.equal(typeof s, "object");
        assert.match(s.path, /^skills\/network-desk-[a-z0-9-]+\/SKILL\.md$/);
        assert.ok(s.description.length > 20);
        assert.deepEqual(s.tools, ["RunAzCliReadCommands", "GetAzCliHelp", "ExecutePythonCode"]);
    }
});
