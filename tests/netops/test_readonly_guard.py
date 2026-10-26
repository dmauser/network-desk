"""Read-only guard: every write is denied, only verified diagnostics are allowed."""

import pytest

from conftest import load_skill_module

guard = load_skill_module("netops-managed-scope", "readonly_guard.py")

READS = [
    "az network vnet list -g rg",
    "az network vnet subnet show -g rg --vnet-name v -n s",
    "az network private-endpoint list -g rg -o json",
    "az network private-dns link vnet list -g rg -z privatelink.blob.core.windows.net",
    "az network private-dns record-set a list -g rg -z privatelink.blob.core.windows.net",
    "az network vpn-connection show -g rg -n c1",
    "az network express-route show -g rg -n er1",
    "az network express-route get-stats -g rg -n er1",
    "az network watcher flow-log list --location eastus",
    "az network vnet list-available-ips -g rg -n v",
    "az resource show --ids /subscriptions/x/resourceGroups/r/providers/Microsoft.App/agents/a",
    "az account management-group show --name mg --expand --recurse",
    "az graph query -q \"Resources | where type =~ 'microsoft.network/publicipaddresses' | project id\"",
    "az monitor metrics list --resource id --metric TunnelAverageBandwidth",
    "az monitor log-analytics query -w ws --analytics-query \"NTANetAnalytics | take 10\"",
    "az rest --url https://management.azure.com/subscriptions/x/providers/Microsoft.Network/virtualNetworks?api-version=2024-05-01",
]

DIAGNOSTICS = [
    ("az network nic show-effective-route-table -g rg -n nic", "effectiveRouteTable/action"),
    ("az network nic list-effective-nsg -g rg -n nic", "effectiveNetworkSecurityGroups/action"),
    ("az network vnet-gateway list-bgp-peer-status -g rg -n gw", "getBgpPeerStatus/action"),
    ("az network vnet-gateway list-learned-routes -g rg -n gw", "getLearnedRoutes/action"),
    ("az network vnet-gateway list-advertised-routes -g rg -n gw --peer 10.0.0.1", "getAdvertisedRoutes/action"),
    ("az network watcher show-next-hop -g rg --vm vm --source-ip 10.0.0.4 --dest-ip 10.1.0.4", "nextHop/action"),
    ("az network watcher test-ip-flow --vm vm -g rg --direction Outbound --protocol TCP "
     "--local 10.0.0.4:60000 --remote 10.1.0.4:443", "ipFlowVerify/action"),
    ("az network express-route list-route-tables -g rg -n er --path primary --peering-name AzurePrivatePeering",
     "routeTables/read"),
    ("az rest --method post --url /subscriptions/x/resourceGroups/r/providers/Microsoft.Network/"
     "networkInterfaces/n/effectiveRouteTable?api-version=2024-05-01", "effectiveRouteTable/action"),
]

DENIED = [
    "az network nsg rule create -g rg --nsg-name n -n r --priority 100",
    "az network nsg rule update -g rg --nsg-name n -n r --access Deny",
    "az network route-table route delete -g rg --route-table-name rt -n r",
    "az network vnet peering sync -g rg --vnet-name v -n p",
    "az network vnet-gateway reset -g rg -n gw",
    "az network vpn-connection shared-key show -g rg --connection-name c",
    "az network vpn-connection show-device-config-script -g rg -n c",
    "az network watcher test-connectivity -g rg --source-resource vm --dest-address 1.1.1.1",
    "az network watcher packet-capture create -g rg --vm vm -n pc",
    "az network watcher run-configuration-diagnostic --resource id",
    "az network application-gateway show-backend-health -g rg -n agw",
    "az network firewall policy deploy -g rg -n p",
    "az resource invoke-action --action restart --ids id",
    "az account set -s sub",
    "az rest --method put --url /subscriptions/x/resourceGroups/r?api-version=2021-04-01",
    "az rest --method patch --url /x",
    "az rest --method delete --url /x",
    "az rest --method post --url /subscriptions/x/providers/Microsoft.Storage/storageAccounts/s/listKeys",
    "az network vnet list; az group delete -n rg --yes",
    "az network vnet list && echo hi",
    "az network vnet list | tee out.txt",
    "az network vnet list > out.txt",
    "az network vnet list $(whoami)",
    "az network vnet frobnicate",
    "kubectl delete pod x",
    "",
]


@pytest.mark.parametrize("command", READS)
def test_reads_are_allowed(command):
    decision = guard.classify_az_command(command)
    assert decision["decision"] == "allow_read", decision


@pytest.mark.parametrize("command,action", DIAGNOSTICS)
def test_verified_diagnostics_are_allowed(command, action):
    decision = guard.classify_az_command(command)
    assert decision["decision"] == "allow_diagnostic", decision
    assert decision["required_permission"].endswith(action)


@pytest.mark.parametrize("command", DENIED)
def test_writes_secrets_and_unknowns_are_denied(command):
    decision = guard.classify_az_command(command)
    assert decision["decision"] == "deny", decision
    with pytest.raises(PermissionError):
        guard.assert_read_only(command)


def test_diagnostic_allowlist_is_exact_and_has_no_writes():
    actions = guard.custom_role_actions()
    assert len(actions) == len(set(a.casefold() for a in actions)) == 9
    for action in actions:
        assert action.startswith("Microsoft.Network/")
        assert action.endswith("/action")
        assert not any(w in action.casefold() for w in ("/write", "/delete", "connectivitycheck",
                                                         "troubleshoot", "packetcapture"))
        assert guard.classify_arm_action(action)["decision"] == "allow_diagnostic"
    for excluded in guard.EXCLUDED_ACTIONS:
        assert guard.classify_arm_action(excluded)["decision"] == "deny"


def test_every_diagnostic_command_maps_to_an_allowed_permission():
    for path, permission in guard.DIAGNOSTIC_COMMANDS.items():
        assert guard.classify_arm_action(permission)["allowed"], (path, permission)


@pytest.mark.parametrize("action,expected", [
    ("Microsoft.Network/virtualNetworks/read", "allow_read"),
    ("microsoft.network/virtualnetworkgateways/getbgppeerstatus/action", "allow_diagnostic"),
    ("Microsoft.Network/networkSecurityGroups/write", "deny"),
    ("Microsoft.Network/routeTables/delete", "deny"),
    ("Microsoft.Network/virtualNetworkGateways/reset/action", "deny"),
    ("", "deny"),
])
def test_classify_arm_action(action, expected):
    assert guard.classify_arm_action(action)["decision"] == expected
