import { test } from "node:test";
import assert from "node:assert/strict";
import { access } from "node:fs/promises";
import { join } from "node:path";
import { REGISTRY, MCP_PROVIDERS, MCP_VALIDATION_DIRECTIVE, MCP_VALIDATION_NOTE } from "../../extensions/network-desk/registry.mjs";
import { EXT_DIR } from "./harness.mjs";

const exists = async (p) => { try { await access(p); return true; } catch { return false; } };

test("registry has 20 well-formed specialists", () => {
    const prefixes = Object.keys(REGISTRY);
    assert.equal(prefixes.length, 20);
    const dirs = new Set();
    for (const [prefix, s] of Object.entries(REGISTRY)) {
        for (const k of ["dir", "domain", "name", "summary", "icon"]) {
            assert.equal(typeof s[k], "string", `${prefix}.${k}`);
            assert.ok(s[k].length > 0, `${prefix}.${k} empty`);
        }
        assert.ok(s.trigger instanceof RegExp, `${prefix}.trigger`);
        assert.ok(Object.keys(s.skills).length > 0, `${prefix} has no skills`);
        assert.ok(!dirs.has(s.dir), `duplicate dir ${s.dir}`);
        dirs.add(s.dir);
    }
});

test("every registry role and skill file exists", async () => {
    for (const s of Object.values(REGISTRY)) {
        assert.ok(await exists(join(EXT_DIR, "specialists", s.dir, "agents", `${s.dir}.md`)), `${s.dir} role`);
        for (const skill of Object.keys(s.skills)) {
            assert.ok(
                await exists(join(EXT_DIR, "specialists", s.dir, "skills", skill, "SKILL.md")),
                `${s.dir}/${skill}`,
            );
        }
    }
});

test("MCP validation policy covers azure, aws, gcp", () => {
    assert.deepEqual(Object.keys(MCP_PROVIDERS).sort(), ["aws", "azure", "gcp"]);
    assert.match(MCP_VALIDATION_DIRECTIVE, /Microsoft Learn/);
    assert.ok(MCP_VALIDATION_NOTE.length > 0);
});
