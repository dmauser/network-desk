#!/usr/bin/env python3
"""Render NetOps scheduled-task API payloads and checked-in YAML references.

Copied from dmauser/finops-sre-agent-pack@ac81cd15dbe1bd821c0abe97bfe19bfcb75c3021
(plugins/finops/scheduled-tasks/render_tasks.py) and adapted for NetOps: canonical task IDs,
per-task email delivery from the manifest, and an optional (possibly empty) retired list.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import textwrap


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "task-manifest.json"
SCOPE_PROMPT = ROOT / "prompts" / "_managed-scope.txt"
EXPECTED_IDS = {
    "hybrid-health",
    "nsg-firewall-audit",
    "pe-dns-validation",
    "exposure-scan",
    "capacity-forecast",
    "kpi-scorecard",
}
EXPECTED_RETIRED_IDS = set()
_TEMPLATE_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def _load_manifest_data():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tasks = data.get("tasks")
    retired = data.get("retiredTasks")
    if (
        data.get("schemaVersion") != 1
        or not isinstance(tasks, list)
        or not isinstance(retired, list)
    ):
        raise ValueError("Unsupported or malformed task manifest")
    ids = {task.get("id") for task in tasks}
    retired_ids = {task.get("id") for task in retired}
    if len(tasks) != len(EXPECTED_IDS) or ids != EXPECTED_IDS:
        raise ValueError("Task manifest must define the canonical six NetOps task IDs")
    if len(retired) != len(EXPECTED_RETIRED_IDS) or retired_ids != EXPECTED_RETIRED_IDS:
        raise ValueError("Task manifest retired tasks do not match the canonical retired IDs")
    if ids & retired_ids:
        raise ValueError("Active and retired task IDs must not overlap")
    for task in tasks:
        prompt_path = ROOT / task["prompt"]
        if not prompt_path.is_file():
            raise ValueError(f"Missing prompt asset: {prompt_path}")
        if task.get("emailImportance") not in ("High", "Normal") or not task.get("emailSubject"):
            raise ValueError(f"Task {task.get('id')} needs emailSubject and emailImportance High|Normal")
    return tasks, retired


def load_manifest():
    return _load_manifest_data()[0]


def load_retired_tasks():
    return _load_manifest_data()[1]


def _env(name, default):
    value = os.environ.get(name)
    return default if value in (None, "") else value


def _plain_value(name, value):
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must be nonempty and contain no control characters")
    return value


def _optional_plain_value(name, value):
    if value in (None, ""):
        return ""
    return _plain_value(name, str(value))


def _task_list(data):
    tasks = data if isinstance(data, list) else data.get("value", [])
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise ValueError("Scheduled-task list response must contain task objects")
    return tasks


def _api_id(value):
    value = _optional_plain_value("scheduled task id", value)
    if value and any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        for char in value
    ):
        raise ValueError("Scheduled task id contains unsupported characters")
    return value


def _delivery(task, reference):
    subject = task["emailSubject"]
    importance = task["emailImportance"]
    if reference:
        return (
            f"if `__ALERT_EMAIL__` is configured, email it with subject `{subject}` and "
            f"{importance} importance; otherwise return it only in the scheduled-task result."
        )
    alert_email = os.environ.get("ALERT_EMAIL", "")
    if alert_email:
        return f"email `{alert_email}` with subject `{subject}` and {importance} importance."
    return (
        "do not send email; ALERT_EMAIL was not set at installation time, so return it "
        "only in the scheduled-task result."
    )


def _special_values(task, reference):
    return {
        "AGENT_RESOURCE_ID": "__AGENT_RESOURCE_ID__" if reference else os.environ["AGENT_RESOURCE_ID"],
        "DELIVERY": _delivery(task, reference),
    }


def _substitute(text, values):
    source_tokens = set(_TEMPLATE_TOKEN.findall(text))
    without_tokens = _TEMPLATE_TOKEN.sub("", text)
    if "{{" in without_tokens or "}}" in without_tokens:
        raise ValueError("Malformed prompt placeholder in source template")
    unknown = source_tokens - values.keys()
    if unknown:
        raise ValueError(
            "Unresolved prompt variables: " + ", ".join(sorted(unknown))
        )
    for key in source_tokens:
        text = text.replace("{{" + key + "}}", values[key])
    return text.strip()


def render_task(task, reference=False):
    values = _special_values(task, reference)
    if task.get("reportNameEnv"):
        values["REPORT_NAME"] = _plain_value(
            task["reportNameEnv"],
            task["defaultReportName"]
            if reference
            else _env(task["reportNameEnv"], task["defaultReportName"]),
        )
    scope = _substitute(SCOPE_PROMPT.read_text(encoding="utf-8"), values)
    prompt = _substitute((ROOT / task["prompt"]).read_text(encoding="utf-8"), values)
    model_default = _env("MODEL_TIER", "ReasoningHeavy")
    name = _plain_value(
        task["nameEnv"],
        task["defaultName"]
        if reference
        else _env(task["nameEnv"], task["defaultName"]),
    )
    cron = _plain_value(
        task["cronEnv"],
        f"__{task['cronEnv']}__"
        if reference
        else _env(task["cronEnv"], task["defaultCron"]),
    )
    agent = _plain_value(
        "TASK_AGENT_NAME",
        "__AGENT_NAME__" if reference else os.environ["TASK_AGENT_NAME"],
    )
    model = _plain_value(
        task["modelEnv"],
        "ReasoningHeavy"
        if reference
        else _env(task["modelEnv"], model_default),
    )
    if not reference and any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        for char in model
    ):
        raise ValueError(f"{task['modelEnv']} contains unsupported characters")
    return {
        "id": task["id"],
        "yaml": task["yaml"],
        "tags": task["tags"],
        "name": name,
        "description": task["description"],
        "cronExpression": cron,
        "agentPrompt": scope + "\n\n" + prompt,
        "agent": agent,
        "agentMode": "autonomous",
        "modelTier": model,
        "owner": "__ALERT_EMAIL__" if reference else os.environ.get("ALERT_EMAIL", ""),
    }


def render_api_payloads():
    return [
        {
            key: value
            for key, value in render_task(task).items()
            if key not in {"id", "yaml", "tags", "owner"}
        }
        for task in select_tasks(load_manifest())
    ]


def _quoted(value):
    return json.dumps(value, ensure_ascii=False)


def render_yaml(task):
    item = render_task(task, reference=True)
    description = textwrap.wrap(item["description"], width=88)
    prompt_lines = item["agentPrompt"].splitlines()
    lines = [
        "# Generated by render_tasks.py from task-manifest.json and prompts/.",
        "# Do not edit this file directly; run: python3 render_tasks.py write",
        "apiVersion: azuresre.ai/v1",
        "kind: ScheduledTask",
        "metadata:",
        f"  name: {_quoted(item['name'])}",
        f"  owner: {_quoted(item['owner'])}",
        "  tags:",
        *(f"    - {tag}" for tag in item["tags"]),
        "spec:",
        f"  name: {_quoted(item['name'])}",
        "  description: >-",
        *(f"    {line}" for line in description),
        f"  agent: {_quoted(item['agent'])}",
        f"  cron: {_quoted(item['cronExpression'])}",
        f"  modelTier: {_quoted(item['modelTier'])}",
        "  agentPrompt: |",
        *(f"    {line}" if line else "" for line in prompt_lines),
    ]
    return "\n".join(lines) + "\n"


def write_or_check(check):
    drift = []
    tasks, retired = _load_manifest_data()
    for task in tasks:
        path = ROOT / task["yaml"]
        expected = render_yaml(task)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                drift.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(expected, encoding="utf-8", newline="\n")
    for task in retired:
        path = ROOT / task["yaml"]
        if path.exists():
            if check:
                drift.append(str(path.relative_to(ROOT)))
            else:
                path.unlink()
    if drift:
        print("Generated scheduled-task YAML drift: " + ", ".join(drift), file=sys.stderr)
        return 1
    return 0


def select_tasks(tasks, selection=None):
    """Filter manifest tasks by TASK_IDS (comma-separated ids; empty or "all" = every task)."""
    raw = os.environ.get("TASK_IDS", "") if selection is None else selection
    wanted = [item.strip() for item in raw.split(",") if item.strip()]
    if not wanted or [item.casefold() for item in wanted] == ["all"]:
        return list(tasks)
    known = [task["id"] for task in tasks]
    unknown = [item for item in wanted if item not in known]
    if unknown:
        raise ValueError(
            "Unknown TASK_IDS: " + ", ".join(unknown) + ". Valid ids: " + ", ".join(known)
        )
    return [task for task in tasks if task["id"] in wanted]


def write_install_plan(existing_path, output_dir):
    tasks, retired = _load_manifest_data()
    tasks = select_tasks(tasks)
    existing = _task_list(json.loads(existing_path.read_text(encoding="utf-8")))
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    expected = {"tasks": [], "retiredNames": []}

    for index, task in enumerate(tasks, start=1):
        payload = {
            key: value
            for key, value in render_task(task).items()
            if key not in {"id", "yaml", "tags", "owner"}
        }
        matches = [item for item in existing if item.get("name") == payload["name"]]
        if len(matches) > 1:
            raise ValueError(f"Multiple scheduled tasks have canonical name: {payload['name']}")
        current = matches[0] if matches else {}
        current_id = _api_id(current.get("id"))
        if matches and not current_id:
            raise ValueError(f"Existing scheduled task has no id: {payload['name']}")
        body_name = f"task-{index}.json"
        (output_dir / body_name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        row = (
            body_name,
            payload["name"],
            payload["agent"],
            payload["cronExpression"],
            current_id,
            _optional_plain_value("scheduled task agent", current.get("agent")),
            _optional_plain_value("scheduled task status", current.get("status")),
        )
        rows.append("\x1f".join(row))
        expected["tasks"].append(
            {"name": payload["name"], "agent": payload["agent"]}
        )

    retired_rows = []
    for task in retired:
        name = _plain_value(
            task["nameEnv"], _env(task["nameEnv"], task["defaultName"])
        )
        expected["retiredNames"].append(name)
        for item in existing:
            if item.get("name") == name:
                retired_id = _api_id(item.get("id"))
                if not retired_id:
                    raise ValueError(f"Retired scheduled task has no id: {name}")
                retired_rows.append(
                    "\x1f".join(
                        (
                            retired_id,
                            name,
                        )
                    )
                )

    report_names = [
        _plain_value(
            task["reportNameEnv"],
            _env(task["reportNameEnv"], task["defaultReportName"]),
        )
        for task in tasks
        if task.get("reportNameEnv")
    ]
    (output_dir / "task-plan.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    (output_dir / "task-count.txt").write_text(f"{len(rows)}\n", encoding="utf-8")
    (output_dir / "retired-plan.tsv").write_text(
        ("\n".join(retired_rows) + "\n") if retired_rows else "",
        encoding="utf-8",
    )
    (output_dir / "reports.txt").write_text(
        "\n".join(report_names) + "\n", encoding="utf-8"
    )
    (output_dir / "expected-tasks.json").write_text(
        json.dumps(expected, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def verify_install(existing_path, expected_path):
    existing = _task_list(json.loads(existing_path.read_text(encoding="utf-8")))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    failures = []
    for item in expected["tasks"]:
        matches = [
            task
            for task in existing
            if task.get("name") == item["name"] and task.get("agent") == item["agent"]
        ]
        if len(matches) != 1:
            failures.append(
                f"expected exactly one task on {item['agent']}: {item['name']}"
            )
    for name in expected["retiredNames"]:
        if any(task.get("name") == name for task in existing):
            failures.append(f"retired task is still present: {name}")
    if failures:
        print("Scheduled-task verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("api", "reports", "write", "check", "install-plan", "verify-install"),
    )
    parser.add_argument(
        "--base64-lines",
        action="store_true",
        help="for api, emit one base64-encoded JSON payload per line",
    )
    parser.add_argument("--existing", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    if args.command == "write":
        return write_or_check(False)
    if args.command == "check":
        return write_or_check(True)
    if args.command == "reports":
        for task in load_manifest():
            if task.get("reportNameEnv"):
                print(_env(task["reportNameEnv"], task["defaultReportName"]))
        return 0
    if args.command == "install-plan":
        if args.existing is None or args.output_dir is None:
            parser.error("install-plan requires --existing and --output-dir")
        write_install_plan(args.existing, args.output_dir)
        return 0
    if args.command == "verify-install":
        if args.existing is None or args.expected is None:
            parser.error("verify-install requires --existing and --expected")
        return verify_install(args.existing, args.expected)

    payloads = render_api_payloads()
    if args.base64_lines:
        for payload in payloads:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            print(base64.b64encode(raw).decode())
    else:
        json.dump(payloads, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
