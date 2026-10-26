"""netscope.py: resource filtering, scope summary and deterministic input persistence."""

import json

import pytest

from conftest import SKILLS, load_json, load_skill_module

netscope = load_skill_module("netops-managed-scope", "netscope.py")
EXAMPLES = SKILLS / "netops-managed-scope" / "examples"

SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"
HUB = f"{SUB}/resourceGroups/rg-netops-hub"


def test_filter_resources_example_fixture():
    managed = load_json(EXAMPLES / "managed-resources.json")
    result = netscope.filter_resources(load_json(EXAMPLES / "inventory.json"), managed)
    assert result["included_count"] == 2
    assert result["excluded_count"] == 1
    assert result["unattributed_count"] == 0
    assert result["excluded"][0]["id"].endswith("vnet-other")


def test_filter_resources_dedupes_casefolds_and_reports_unattributed():
    rows = [
        {"id": f"{HUB}/providers/Microsoft.Network/virtualNetworks/v1"},
        {"ResourceId": f"{HUB.upper()}/PROVIDERS/Microsoft.Network/virtualNetworks/V1"},
        {"_ResourceId": f"{SUB}/resourceGroups/elsewhere/providers/Microsoft.Network/publicIPAddresses/p"},
        f"{HUB}/providers/Microsoft.Network/networkSecurityGroups/n1",
        {"name": "no-id"},
        {"id": "not-an-arm-id"},
    ]
    result = netscope.filter_resources(rows, [HUB])
    assert result["included_count"] == 2
    assert result["duplicate_count"] == 1
    assert result["excluded_count"] == 1
    assert result["unattributed_count"] == 2
    assert result["coverage_pct"] == 40.0
    codes = sorted(d["code"] for d in result["diagnostics"])
    assert codes == ["invalid_resource_id", "unattributed_resource"]


def test_filter_resources_reports_unexpanded_management_groups():
    mg = "/providers/Microsoft.Management/managementGroups/corp"
    result = netscope.filter_resources([f"{HUB}/providers/Microsoft.Network/virtualNetworks/v"], [mg])
    assert result["unexpanded_management_groups"]
    assert result["included_count"] == 0


def test_scope_summary():
    assert netscope.scope_summary([HUB, SUB + "2"]) .startswith("Managed scope: ")
    assert netscope.scope_summary([HUB]) == "Managed scope: 1 resource group"


def test_decide_scope_policy_is_reexported_with_finops_semantics():
    decision = netscope.decide_scope_policy([f"{SUB}/resourceGroups/other"], [HUB], mode="scheduled")
    assert decision["state"] == "outside_managed_scope" and not decision["allowed"]


def test_save_and_load_netops_input_roundtrip(tmp_path):
    directory = tmp_path / "netops-data"
    path = netscope.save_netops_input("bgp-peers", '{"value": [1]}', directory=str(directory))
    assert path.endswith("bgp-peers.json")
    assert netscope.load_netops_input("bgp-peers", directory=str(directory)) == {"value": [1]}
    assert netscope.load_netops_input("missing", directory=str(directory), default=None) is None
    with pytest.raises(FileNotFoundError):
        netscope.load_netops_input("missing", directory=str(directory))


def test_save_netops_input_unwraps_tool_output(tmp_path):
    wrapped = tmp_path / "tool.json"
    wrapped.write_text(json.dumps({"cliExecutionResult": {"output": json.dumps([{"a": 1}])}}))
    netscope.save_netops_input("gateways", source_path=str(wrapped), directory=str(tmp_path / "d"))
    assert netscope.load_netops_input("gateways", directory=str(tmp_path / "d")) == [{"a": 1}]


@pytest.mark.parametrize("name", ["", "Bad", "../x", "a" * 65, None])
def test_save_netops_input_rejects_bad_names(tmp_path, name):
    with pytest.raises(ValueError):
        netscope.save_netops_input(name, {}, directory=str(tmp_path))


def test_save_netops_input_requires_exactly_one_source(tmp_path):
    with pytest.raises(ValueError):
        netscope.save_netops_input("x", directory=str(tmp_path))
    with pytest.raises(ValueError):
        netscope.save_netops_input("x", {}, source_path="y", directory=str(tmp_path))
