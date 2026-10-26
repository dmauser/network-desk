"""Read-only guard for NetOps skills.

Pure, dependency-free, deterministic logic. This module never calls Azure. It
classifies an Azure CLI command (or an ARM authorization action) before a skill
runs it:

* ``allow_read``       - a GET/list/show/query style read.
* ``allow_diagnostic`` - a documented read-equivalent diagnostic that ARM models as
  a POST (for example NIC effective routes or VPN gateway BGP peer status). These
  return state; they never change configuration.
* ``deny``             - everything else, including every create/update/delete/set,
  ``az rest`` with a non-GET method outside the allowlist, shell operators, and any
  command the guard does not recognize (fail closed).

Remediation is never executed by the agent: skills emit a script for a human to
review and run.

Verified sources (Microsoft Learn):
* https://learn.microsoft.com/azure/role-based-access-control/permissions/networking
* https://learn.microsoft.com/azure/network-watcher/required-rbac-permissions
* https://learn.microsoft.com/cli/azure/network/nic
* https://learn.microsoft.com/cli/azure/network/vnet-gateway
* https://learn.microsoft.com/cli/azure/network/express-route
* https://learn.microsoft.com/cli/azure/network/watcher
"""

from __future__ import annotations

import re
import shlex

# Read-equivalent ARM actions that Reader (*/read) does NOT grant. These are the only
# non-read actions in the "NetOps Network Diagnostics Reader" custom role.
DIAGNOSTIC_ACTIONS = (
    "Microsoft.Network/networkInterfaces/effectiveRouteTable/action",
    "Microsoft.Network/networkInterfaces/effectiveNetworkSecurityGroups/action",
    "Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action",
    "Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action",
    "Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action",
    "Microsoft.Network/networkWatchers/nextHop/action",
    "Microsoft.Network/networkWatchers/ipFlowVerify/action",
    "Microsoft.Network/networkWatchers/securityGroupView/action",
    "Microsoft.Network/networkWatchers/topology/action",
)

# Explicitly excluded even though they look diagnostic: they can create resources,
# install VM extensions, or start captures.
EXCLUDED_ACTIONS = (
    "Microsoft.Network/networkWatchers/connectivityCheck/action",
    "Microsoft.Network/networkWatchers/troubleshoot/action",
    "Microsoft.Network/networkWatchers/packetCaptures/write",
    "Microsoft.Network/networkWatchers/connectionMonitors/write",
)

# POST-backed CLI commands that return state only -> required ARM permission.
DIAGNOSTIC_COMMANDS = {
    ("network", "nic", "show-effective-route-table"):
        "Microsoft.Network/networkInterfaces/effectiveRouteTable/action",
    ("network", "nic", "list-effective-nsg"):
        "Microsoft.Network/networkInterfaces/effectiveNetworkSecurityGroups/action",
    ("network", "vnet-gateway", "list-bgp-peer-status"):
        "Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action",
    ("network", "vnet-gateway", "list-learned-routes"):
        "Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action",
    ("network", "vnet-gateway", "list-advertised-routes"):
        "Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action",
    ("network", "watcher", "show-next-hop"):
        "Microsoft.Network/networkWatchers/nextHop/action",
    ("network", "watcher", "test-ip-flow"):
        "Microsoft.Network/networkWatchers/ipFlowVerify/action",
    ("network", "watcher", "show-security-group-view"):
        "Microsoft.Network/networkWatchers/securityGroupView/action",
    ("network", "watcher", "show-topology"):
        "Microsoft.Network/networkWatchers/topology/action",
    # ExpressRoute peering tables are POST in ARM but authorized by */read (Reader).
    ("network", "express-route", "list-route-tables"):
        "Microsoft.Network/expressRouteCircuits/peerings/routeTables/read",
    ("network", "express-route", "list-route-tables-summary"):
        "Microsoft.Network/expressRouteCircuits/peerings/routeTablesSummary/read",
    ("network", "express-route", "list-arp-tables"):
        "Microsoft.Network/expressRouteCircuits/peerings/arpTables/read",
}

# Data-plane reads (query APIs) that are reads even when the transport is POST.
READ_QUERY_COMMANDS = {
    ("graph", "query"),
    ("monitor", "log-analytics", "query"),
    ("monitor", "metrics", "list"),
    ("monitor", "metrics", "list-definitions"),
    ("monitor", "metrics", "list-namespaces"),
}

# az rest POST paths allowed because they map to DIAGNOSTIC_ACTIONS.
_REST_DIAGNOSTIC_SUFFIXES = {
    "/effectiveroutetable": DIAGNOSTIC_ACTIONS[0],
    "/effectivenetworksecuritygroups": DIAGNOSTIC_ACTIONS[1],
    "/getbgppeerstatus": DIAGNOSTIC_ACTIONS[2],
    "/getlearnedroutes": DIAGNOSTIC_ACTIONS[3],
    "/getadvertisedroutes": DIAGNOSTIC_ACTIONS[4],
    "/nexthop": DIAGNOSTIC_ACTIONS[5],
    "/ipflowverify": DIAGNOSTIC_ACTIONS[6],
    "/securitygroupview": DIAGNOSTIC_ACTIONS[7],
    "/topology": DIAGNOSTIC_ACTIONS[8],
}

_READ_VERBS = {"list", "show", "query", "get-stats", "list-available-ips",
               "check-ip-address", "list-definitions", "list-namespaces",
               "list-sub", "list-mapping", "list-nic", "list-endpoint-services",
               "show-sub-under-mg", "list-by-virtual-network", "list-types"}
_READ_VERB_RE = re.compile(r"^(list|show)(-[a-z0-9-]+)?$")
_WRITE_VERB_RE = re.compile(
    r"^(create|delete|update|set|add|remove|start|stop|restart|reset|patch|tag|move|"
    r"invoke-action|import|deploy|sync|configure|enable|disable|purge|"
    r"start-.*|stop-.*|run-.*|test-connectivity|upgrade|attach|detach|login|logout|"
    r"wait|assign|unassign|regenerate.*|rotate.*|put|post)$"
)
# Read-looking commands that reveal secrets, or are POST-backed with an action that
# is not in DIAGNOSTIC_ACTIONS. Denied by command-path token.
_SECRET_OR_UNVERIFIED_TOKENS = {
    "shared-key", "keys", "list-keys", "key", "secret", "secrets", "credential",
    "credentials", "show-connection-string", "show-device-config-script",
    "list-ike-sas", "show-backend-health", "vpn-client", "generate-vpn-profile",
    "list-service-sas", "list-account-sas", "export",
}
_SHELL_OPERATORS = {";", "&&", "||", "|", ">", ">>", "<", "&", "`", "$("}
_CONTEXT_MUTATING = {("account", "set"), ("account", "clear"), ("config", "set"),
                     ("extension", "add"), ("extension", "remove"), ("upgrade",)}


def _result(decision, reason, command=None, permission=None):
    return {
        "decision": decision,
        "allowed": decision != "deny",
        "reason": reason,
        "command": command,
        "required_permission": permission,
    }


def _tokenize(command):
    if isinstance(command, (list, tuple)):
        return [str(token) for token in command], False
    lexer = shlex.shlex(str(command), posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    tokens = list(lexer)
    has_operator = any(token in _SHELL_OPERATORS or set(token) <= set(";&|<>")
                       for token in tokens)
    if "`" in str(command) or "$(" in str(command):
        has_operator = True
    return tokens, has_operator


def _option_value(tokens, *names):
    for index, token in enumerate(tokens):
        for name in names:
            if token == name and index + 1 < len(tokens):
                return tokens[index + 1]
            if token.startswith(name + "="):
                return token.split("=", 1)[1]
    return None


def _command_path(tokens):
    path = []
    for token in tokens[1:]:
        if token.startswith("-"):
            break
        path.append(token.casefold())
    return tuple(path)


def classify_arm_action(action):
    """Classify an ARM authorization action string."""

    value = str(action or "").strip()
    folded = value.casefold()
    if not folded:
        return _result("deny", "empty_action")
    if folded in {item.casefold() for item in EXCLUDED_ACTIONS}:
        return _result("deny", "excluded_diagnostic", permission=value)
    if folded in {item.casefold() for item in DIAGNOSTIC_ACTIONS}:
        return _result("allow_diagnostic", "read_equivalent_diagnostic", permission=value)
    if folded.endswith("/read"):
        return _result("allow_read", "read_action", permission=value)
    return _result("deny", "write_or_unknown_action", permission=value)


def _classify_rest(tokens, command):
    method = (_option_value(tokens, "--method", "-m") or "get").casefold()
    url = _option_value(tokens, "--url", "--uri", "-u") or ""
    path = url.split("?", 1)[0].rstrip("/").casefold()
    if method == "get":
        return _result("allow_read", "rest_get", command)
    if method == "post":
        for suffix, permission in _REST_DIAGNOSTIC_SUFFIXES.items():
            if path.endswith(suffix):
                return _result("allow_diagnostic", "rest_post_diagnostic", command, permission)
        if path.endswith("/providers/microsoft.resourcegraph/resources"):
            return _result("allow_read", "resource_graph_query", command)
    return _result("deny", f"rest_{method}_not_allowed", command)


def classify_az_command(command):
    """Classify one Azure CLI command. Unknown commands are denied (fail closed)."""

    try:
        tokens, has_operator = _tokenize(command)
    except ValueError as error:
        return _result("deny", f"unparseable_command: {error}", str(command))
    text = command if isinstance(command, str) else " ".join(tokens)
    if not tokens or tokens[0].casefold() != "az":
        return _result("deny", "not_an_az_command", text)
    if has_operator:
        return _result("deny", "shell_operator_not_allowed", text)
    path = _command_path(tokens)
    if not path:
        return _result("deny", "missing_command_group", text)
    if path[0] == "rest":
        return _classify_rest(tokens, text)
    for mutating in _CONTEXT_MUTATING:
        if path[: len(mutating)] == mutating:
            return _result("deny", "mutates_cli_context", text)
    blocked = [token for token in path if token in _SECRET_OR_UNVERIFIED_TOKENS]
    if blocked:
        return _result("deny", f"secret_or_unverified:{blocked[0]}", text)
    if path in DIAGNOSTIC_COMMANDS:
        return _result("allow_diagnostic", "read_equivalent_diagnostic", text,
                       DIAGNOSTIC_COMMANDS[path])
    if path in READ_QUERY_COMMANDS:
        return _result("allow_read", "read_query", text)
    verb = path[-1]
    if _WRITE_VERB_RE.match(verb):
        return _result("deny", f"write_verb:{verb}", text)
    if verb in _READ_VERBS or _READ_VERB_RE.match(verb):
        return _result("allow_read", "read_verb", text)
    return _result("deny", f"unknown_verb:{verb}", text)


def assert_read_only(command):
    """Raise PermissionError unless ``command`` is allowed; return the decision."""

    decision = classify_az_command(command)
    if not decision["allowed"]:
        raise PermissionError(
            f"NetOps read-only guard denied command ({decision['reason']}): {decision['command']}"
        )
    return decision


def custom_role_actions():
    """Actions for the 'NetOps Network Diagnostics Reader' custom role."""

    return sorted(DIAGNOSTIC_ACTIONS, key=str.casefold)
