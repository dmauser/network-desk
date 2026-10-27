#!/usr/bin/env python3
"""Validate NetOps incident response plan specs and print portal / azmcp configuration.

Usage:
  python validate_plans.py check                 # validate every *.yaml against schema.json + semantics
  python validate_plans.py portal                # print the portal fields per plan
  python validate_plans.py azmcp --agent NAME [--resource-group RG]
                                                 # print `azmcp sreagent incidents plans create` commands
                                                 # for a HUMAN to run (the agent never creates plans)

Requires PyYAML (dev dependency); the SRE Agent runtime never imports this file.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SCHEMA = HERE / "schema.json"
ROUTING = PLUGIN / "agents" / "routing.json"

# Metric names verified on the Azure Monitor supported-metrics reference pages (cited in each plan).
VERIFIED_METRICS = {
    "Microsoft.Network/virtualNetworkGateways": {
        "BgpPeerStatus", "BgpRoutesLearned", "BgpRoutesAdvertised", "TunnelAverageBandwidth",
        "TunnelEgressPacketDropCount", "TunnelIngressPacketDropCount", "TunnelEgressBytes", "TunnelIngressBytes",
    },
    "Microsoft.Network/expressRouteCircuits": {"BgpAvailability", "ArpAvailability", "BitsInPerSecond", "BitsOutPerSecond"},
    "Microsoft.Network/loadBalancers": {
        "AllocatedSnatPorts", "UsedSnatPorts", "SnatConnectionCount", "DipAvailability", "VipAvailability",
    },
    "Microsoft.Network/natGateways": {"SNATConnectionCount", "PacketDropCount", "DatapathAvailability", "TotalConnectionCount"},
    "Microsoft.Network/azureFirewalls": {"SNATPortUtilization", "FirewallLatencyPng", "FirewallHealth", "Throughput"},
    "Microsoft.Network/privateEndpoints": {"PEBytesIn", "PEBytesOut"},
}

WRITE_VERBS = re.compile(r"\b(az\s+\S+.*\s(create|delete|update|set|reset|start|stop|restart)\b|--yes\b)", re.I)


def _yaml():
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required: pip install -r requirements-dev.txt") from exc
    return yaml


def _type_ok(value, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    raise ValueError(f"unsupported schema type {expected}")


def validate_schema(value, schema: dict, path: str = "$") -> list[str]:
    """Minimal JSON-Schema subset: type, required, properties, additionalProperties=false,
    items, minItems, enum, pattern, minimum, maximum."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected and not _type_ok(value, expected):
        return [f"{path}: expected {expected}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected property '{key}'")
        for key, sub in props.items():
            if key in value:
                errors.extend(validate_schema(value[key], sub, f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate_schema(item, schema["items"], f"{path}[{i}]"))
    return errors


def load_plans() -> list[tuple[Path, dict]]:
    yaml = _yaml()
    return [(p, yaml.safe_load(p.read_text(encoding="utf-8"))) for p in sorted(HERE.glob("*.yaml"))]


def _routing_skills() -> set[str]:
    routing = json.loads(ROUTING.read_text(encoding="utf-8"))
    return {s["skill"] for s in routing["skills"]} | {routing["fallbackSkill"]}


def semantic_errors(plan: dict, skills: set[str]) -> list[str]:
    errors: list[str] = []
    inv = plan.get("investigation", {})
    for skill in [inv.get("primarySkill"), *inv.get("followupSkills", [])]:
        if skill not in skills:
            errors.append(f"unknown skill {skill!r}")
    if inv.get("primarySkill") in inv.get("followupSkills", []):
        errors.append("primarySkill repeated in followupSkills")
    steps = inv.get("steps", [])
    if not steps or "netops-managed-scope" not in steps[0]:
        errors.append("first step must resolve the managed scope (netops-managed-scope)")
    if not any("netops-report-renderer" in s for s in steps):
        errors.append("a step must render the report with netops-report-renderer")
    for step in steps:
        if ";" in step:
            errors.append(f"step contains ';' (azmcp --steps separator): {step!r}")
        if WRITE_VERBS.search(step):
            errors.append(f"step looks like a write operation: {step!r}")
    for sig in plan.get("alertSignals", []):
        allowed = VERIFIED_METRICS.get(sig.get("resourceType"), set())
        if sig.get("metric") not in allowed:
            errors.append(f"unverified metric {sig.get('resourceType')}/{sig.get('metric')}")
    cites = plan.get("citations", [])
    if "https://learn.microsoft.com/azure/sre-agent/incident-response-plans" not in cites:
        errors.append("must cite the incident response plans doc")
    return errors


def check() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    skills = _routing_skills()
    plans = load_plans()
    failures = 0
    names: set[str] = set()
    titles: set[str] = set()
    for path, plan in plans:
        errs = validate_schema(plan, schema) + semantic_errors(plan, skills)
        name = (plan.get("metadata") or {}).get("name")
        title = (plan.get("filter") or {}).get("titleContains")
        if name in names:
            errs.append(f"duplicate plan name {name}")
        if title in titles:
            errs.append(f"duplicate titleContains {title}")
        names.add(name)
        titles.add(title)
        for e in errs:
            print(f"{path.name}: {e}", file=sys.stderr)
        failures += bool(errs)
    if not plans:
        print("no plans found", file=sys.stderr)
        return 1
    print(f"{len(plans)} plan(s) checked, {failures} with errors")
    return 1 if failures else 0


def portal() -> int:
    for _, plan in load_plans():
        f, h = plan["filter"], plan["handler"]
        cd = h["reinvestigationCooldown"]
        print(f"# {plan['metadata']['displayName']}")
        print(f"Incident response plan name : {plan['metadata']['name']}")
        print(f"Severity                    : {', '.join(f['severities'])}")
        print(f"Title contains              : {f['titleContains']}")
        print(f"Response custom agent       : {h['customAgent']}")
        print(f"Agent autonomy level        : {h['autonomy']}")
        print(f"Reinvestigation cooldown    : {'on' if cd['enabled'] else 'off'}, {cd['hours']}h")
        print()
    return 0


def azmcp(agent: str, resource_group: str | None) -> int:
    print("# Review, then run manually. Creating a plan changes SRE Agent configuration; the agent never runs this.")
    for _, plan in load_plans():
        m = plan["azureMcp"]
        steps = ";".join(plan["investigation"]["steps"])
        cmd = [
            "azmcp", "sreagent", "incidents", "plans", "create",
            "--agent", agent,
            "--name", plan["metadata"]["name"],
            "--severity", m["severity"],
            "--trigger-condition", m["triggerCondition"],
            "--services", *m["services"],
            "--steps", steps,
            "--agent-mode", m["agentMode"],
        ]
        if resource_group:
            cmd += ["--resource-group", resource_group]
        print(" ".join(shlex.quote(c) for c in cmd))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("portal")
    p = sub.add_parser("azmcp")
    p.add_argument("--agent", required=True)
    p.add_argument("--resource-group")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        return check()
    if args.cmd == "portal":
        return portal()
    return azmcp(args.agent, args.resource_group)


if __name__ == "__main__":
    raise SystemExit(main())
