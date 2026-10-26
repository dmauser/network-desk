"""NetOps resource scoping and deterministic input persistence.

Pure, dependency-free logic built on ``scope.py`` (copied verbatim from FinOps). It
never calls Azure. Skills retrieve resource inventories (Resource Graph, ``az ... list``)
and pass them here to keep only resources inside the agent's managed scope, with exact
coverage reporting. ``save_netops_input``/``load_netops_input`` mirror FinOps
``save_finops_input``/``load_finops_input`` (dmauser/finops-sre-agent-pack@ac81cd15,
plugins/finops/skills/finops-managed-scope/usage.py) with the directory renamed to
``tmp/netops-data``.
"""

from __future__ import annotations

import json
import os
import re
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_scope():
    path = Path(__file__).with_name("scope.py")
    spec = spec_from_file_location("netops_managed_scope", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load managed-scope helpers from {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scope = _load_scope()
resolve_managed_scopes = _scope.resolve_managed_scopes
decide_scope_policy = _scope.decide_scope_policy
canonicalize_resource_id = _scope.canonicalize_resource_id

_ID_KEYS = ("id", "resourceId", "resource_id", "ResourceId", "_ResourceId")


def _resource_id(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in _ID_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def filter_resources(resources, managed_scopes, *, management_group_expansions=None):
    """Split resources into included / excluded / unattributed by managed scope.

    ``resources`` may be ARM resource dicts (``id``), Resource Graph rows, Log Analytics
    rows (``_ResourceId``/``ResourceId``) or bare resource IDs. Duplicates (case-insensitive
    ID) are removed. Returns counts, ``coverage_pct`` and deterministic diagnostics.
    """

    resolved = resolve_managed_scopes(
        managed_scopes, management_group_expansions=management_group_expansions
    )
    index = _scope._containment_index(resolved)
    included, excluded, unattributed, diagnostics = [], [], [], list(resolved["diagnostics"])
    seen = set()
    duplicates = 0
    for position, item in enumerate(list(resources or ())):
        raw = _resource_id(item)
        if raw is None:
            unattributed.append(item)
            diagnostics.append({"code": "unattributed_resource",
                                "message": f"Resource {position} has no resource ID"})
            continue
        try:
            canonical = canonicalize_resource_id(raw)
        except ValueError as error:
            unattributed.append(item)
            diagnostics.append({"code": "invalid_resource_id",
                                "message": f"Resource {position}: {error}"})
            continue
        key = canonical.casefold()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        decision = _scope._evaluate_indexed_containment(resolved, index, canonical)
        (included if decision["contained"] else excluded).append(item)
    attributable = len(included) + len(excluded)
    total = attributable + len(unattributed)
    return {
        "included": included,
        "excluded": excluded,
        "unattributed": unattributed,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "unattributed_count": len(unattributed),
        "duplicate_count": duplicates,
        "coverage_pct": round(100.0 * len(included) / total, 2) if total else 100.0,
        "unexpanded_management_groups": list(resolved["unexpanded_management_groups"]),
        "diagnostics": diagnostics,
    }


def scope_summary(managed_scopes, *, management_group_expansions=None):
    """One-line human summary of the effective scope for report headers."""

    resolved = resolve_managed_scopes(
        managed_scopes, management_group_expansions=management_group_expansions
    )
    parts = []
    for label, key in (("management group", "management_group_scopes"),
                       ("subscription", "subscription_scopes"),
                       ("resource group", "resource_group_scopes")):
        count = len(resolved[key])
        if count:
            parts.append(f"{count} {label}{'s' if count != 1 else ''}")
    return "Managed scope: " + (", ".join(parts) if parts else "none")


# --- deterministic input persistence (mirrors FinOps usage.py) -----------------------

_INPUT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MISSING = object()
DEFAULT_DIRECTORY = "tmp/netops-data"


def _unwrap_tool_output(data):
    """Peel RunAzCliReadCommands wrappers (`cliExecutionResult.output` JSON strings)."""

    for _ in range(4):
        if not isinstance(data, dict) or isinstance(data.get("value"), list):
            return data
        inner = data.get("cliExecutionResult") or data
        output = inner.get("output") if isinstance(inner, dict) else None
        if not isinstance(output, str):
            return data
        try:
            data = json.loads(output)
        except ValueError:
            return None
    return data


def _read_tool_output(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def save_netops_input(name, data=None, *, source_path=None, directory=DEFAULT_DIRECTORY):
    """Persist one Azure response to `<directory>/<name>.json`. Returns the path."""

    if not isinstance(name, str) or not _INPUT_NAME.match(name):
        raise ValueError(f"invalid input name {name!r}; use lowercase letters, digits, '-' or '_'")
    if (data is None) == (source_path is None):
        raise ValueError("pass exactly one of data or source_path")
    if source_path is not None:
        raw = _read_tool_output(source_path)
        if raw is None:
            raise ValueError(f"tool output is missing or not JSON: {source_path}")
        data = _unwrap_tool_output(raw)
        if data is None:
            raise ValueError(f"tool output holds no JSON response (failed call?): {source_path}")
    elif isinstance(data, str):
        data = json.loads(data)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.json")
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, default=str)
    os.replace(temp, path)
    return path


def load_netops_input(name, directory=DEFAULT_DIRECTORY, default=_MISSING):
    """Load an input written by `save_netops_input`; return `default` (when given) if absent."""

    if not isinstance(name, str) or not _INPUT_NAME.match(name):
        raise ValueError(f"invalid input name {name!r}")
    path = os.path.join(directory, f"{name}.json")
    if not os.path.exists(path):
        if default is _MISSING:
            raise FileNotFoundError(path)
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
