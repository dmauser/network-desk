"""NetOps eval runner: injected fault -> expected skill routing -> expected finding.

Each fixture in ``fixtures/*.json`` models a fault from the NetOps labs
(https://github.com/dmauser/azure-sre-netops SC-01..SC-08 and
https://github.com/dmauser/az-srenetops-microhack). The runner:

1. routes the operator symptom with the same scoring as ``netops-investigator``
   (``plugins/netops/agents/routing.json``: count of matching symptom regexes,
   ties broken by ``order``, fallback skill when nothing matches);
2. runs the expected skill's deterministic engine on the fixture's collected
   evidence (the read-only data the agent would gather);
3. checks the expected findings, the severity ceiling and the evidence gaps.

Stdlib only. ``python evals/netops/run.py`` prints a table and exits 1 on failure.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLUGIN = ROOT / "plugins" / "netops"
FIXTURES = HERE / "fixtures"
SEVERITIES = ("critical", "high", "medium", "low", "info")

# skill -> engine file inside plugins/netops/skills/<skill>/
ENGINES = {
    "netops-hybrid-health": "hybrid.py",
    "netops-private-endpoint-dns": "pedns.py",
}


def load_routing():
    return json.loads((PLUGIN / "agents" / "routing.json").read_text(encoding="utf-8"))


def route(symptom, routing=None):
    """Return ranked [(skill, score)] for a symptom; fallback skill when nothing matches."""

    routing = routing or load_routing()
    flags = re.IGNORECASE if "i" in routing.get("flags", "") else 0
    scored = []
    for entry in routing["skills"]:
        score = sum(1 for pattern in entry["symptoms"] if re.search(pattern, symptom, flags))
        if score:
            scored.append((-score, entry["order"], entry["skill"]))
    if not scored:
        return [(routing["fallbackSkill"], 0)]
    return [(skill, -neg) for neg, _order, skill in sorted(scored)]


def load_engine(skill):
    filename = ENGINES.get(skill)
    if not filename:
        raise KeyError(f"no engine registered for {skill}")
    path = PLUGIN / "skills" / skill / filename
    spec = importlib.util.spec_from_file_location(f"eval_{skill.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_fixture(path):
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("id", "title", "source", "injected_fault", "symptom", "expected_skill", "expect"):
        if key not in fixture:
            raise ValueError(f"{Path(path).name}: missing '{key}'")
    if ("input" in fixture) == ("input_ref" in fixture):
        raise ValueError(f"{Path(path).name}: exactly one of 'input' or 'input_ref' is required")
    if "input_ref" in fixture:
        fixture["input"] = json.loads((ROOT / fixture["input_ref"]).read_text(encoding="utf-8"))
    return fixture


def evaluate(fixture, routing=None):
    """Run one scenario; return {id, routed, passed, failures[]}."""

    failures = []
    ranked = route(fixture["symptom"], routing)
    routed = ranked[0][0]
    if routed != fixture["expected_skill"]:
        failures.append(f"routed to {routed}, expected {fixture['expected_skill']}")

    result = load_engine(fixture["expected_skill"]).analyze(fixture["input"])
    ids = [f["id"] for f in result["findings"]]
    expect = fixture["expect"]

    for prefix in expect.get("finding_prefixes", []):
        if not any(i.startswith(prefix) for i in ids):
            failures.append(f"missing finding {prefix}*")
    for prefix in expect.get("absent_prefixes", []):
        if any(i.startswith(prefix) for i in ids):
            failures.append(f"unexpected finding {prefix}*")
    if "top_severity" in expect:
        top = result["findings"][0]["severity"] if result["findings"] else None
        if top != expect["top_severity"]:
            failures.append(f"top severity {top}, expected {expect['top_severity']}")
    if "max_severity" in expect:
        ceiling = SEVERITIES.index(expect["max_severity"])
        worse = [f["id"] for f in result["findings"] if SEVERITIES.index(f["severity"]) < ceiling]
        if worse:
            failures.append(f"findings above {expect['max_severity']}: {worse}")
    for text in expect.get("evidence_gap_contains", []):
        if not any(text in g for g in result["evidence_gaps"]):
            failures.append(f"missing evidence gap containing '{text}'")
    if "partial" in expect and result["partial"] is not expect["partial"]:
        failures.append(f"partial={result['partial']}, expected {expect['partial']}")

    return {"id": fixture["id"], "routed": routed, "passed": not failures, "failures": failures,
            "finding_ids": ids}


def fixture_paths():
    return sorted(FIXTURES.glob("*.json"))


def main(argv=None):
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])] or fixture_paths()
    routing = load_routing()
    results = [evaluate(load_fixture(p), routing) for p in paths]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{status}  {r['id']:<10} -> {r['routed']}")
        for failure in r["failures"]:
            print(f"      - {failure}")
    passed = sum(r["passed"] for r in results)
    print(f"{passed}/{len(results)} scenarios passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
