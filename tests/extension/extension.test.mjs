// Behavioral contract for the Copilot CLI extension (extension.mjs).
//
// Drives every registered tool and session hook through the SDK stub and
// compares the full transcript to tests/extension/golden/behavior.json, so any
// change in extension behavior is caught. Regenerate intentionally with:
//   UPDATE_GOLDEN=1 npm run test:extension
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { loadExtension, text, REPO_ROOT } from "./harness.mjs";
import { REGISTRY } from "../../extensions/network-desk/registry.mjs";

const GOLDEN = join(REPO_ROOT, "tests", "extension", "golden", "behavior.json");
const norm = (s) => s.replace(/\r\n/g, "\n");
const digest = (s) => createHash("sha256").update(norm(s)).digest("hex");

const ROUTE_QUERIES = [
    "design a hub-spoke VNet topology across 3 regions",
    "audit my Azure Firewall rules for shadowed entries",
    "my site-to-site VPN BGP session keeps flapping",
    "private endpoint DNS resolution returns public IP",
    "SNAT port exhaustion on the load balancer",
    "what's the weather",
];

const PROMPTS = [
    "hello there",
    "what can network-desk do?",
    "my ExpressRoute BGP peering is down and the VPN tunnel flaps",
    "ExpressRoute again — check BGP",
    "private endpoint DNS for storage and NSG audit",
];

async function transcript() {
    const ext = await loadExtension();
    const out = {};
    out.tools = ext.config.tools.map((t) => ({
        name: t.name,
        description: t.description,
        parameters: t.parameters,
        skipPermission: t.skipPermission,
    }));
    out.capabilities = digest(text(await ext.tools.cn_capabilities.handler({})));
    out.route = {};
    for (const q of ROUTE_QUERIES) out.route[q] = digest(text(await ext.tools.cn_route.handler({ query: q })));
    out.role = {};
    out.orchestrate = {};
    out.skill = {};
    for (const [prefix, spec] of Object.entries(REGISTRY)) {
        out.role[prefix] = digest(text(await ext.tools.cn_role.handler({ specialist: `cn_${prefix}` })));
        out.orchestrate[prefix] = digest(text(await ext.tools.cn_orchestrate.handler({ specialist: prefix })));
        for (const skill of Object.keys(spec.skills)) {
            out.skill[`${prefix}/${skill}`] = digest(
                text(await ext.tools.cn_skill.handler({ specialist: `cn_${prefix}`, skill })),
            );
        }
    }
    out.skillLegacy = digest(text(await ext.tools.cn_skill.handler({ skill: "cn_vnet_skill_address_planner" })));
    out.unknownSpecialist = digest(text(await ext.tools.cn_role.handler({ specialist: "nope" })));
    out.unknownSkill = digest(text(await ext.tools.cn_skill.handler({ specialist: "cn_fw", skill: "nope" })));
    out.sessionStart = digest(JSON.stringify(await ext.hooks.onSessionStart({})));
    out.prompts = [];
    for (const p of PROMPTS) {
        const r = await ext.hooks.onUserPromptSubmitted({ prompt: p });
        out.prompts.push(r === undefined ? null : digest(r.additionalContext));
    }
    return out;
}

test("extension registers exactly the 5 parameterized cn_* tools", async () => {
    const ext = await loadExtension();
    assert.deepEqual(
        ext.config.tools.map((t) => t.name).sort(),
        ["cn_capabilities", "cn_orchestrate", "cn_role", "cn_route", "cn_skill"],
    );
    for (const t of ext.config.tools) assert.equal(t.skipPermission, true, `${t.name} skipPermission`);
});

test("role and skill tools carry the validation policy and load real content", async () => {
    const ext = await loadExtension();
    for (const prefix of Object.keys(REGISTRY)) {
        const role = text(await ext.tools.cn_role.handler({ specialist: `cn_${prefix}` }));
        assert.ok(role.length > 500, `role for ${prefix} unexpectedly short`);
        assert.doesNotMatch(role, /Failed to load|ENOENT/, `role for ${prefix}`);
    }
});

test("extension behavior matches golden transcript", async () => {
    const actual = await transcript();
    if (process.env.UPDATE_GOLDEN === "1") {
        await writeFile(GOLDEN, JSON.stringify(actual, null, 2) + "\n");
        return;
    }
    const expected = JSON.parse(await readFile(GOLDEN, "utf8"));
    assert.deepEqual(actual, expected);
});
