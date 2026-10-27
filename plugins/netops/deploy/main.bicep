// NetOps SRE Agent — infrastructure (phase 1 of deploy.sh).
// Adapted from dmauser/finops-sre-agent-pack@ac81cd15dbe1bd821c0abe97bfe19bfcb75c3021
// (plugins/finops/deploy/main.bicep). Creates the resource group, the SRE Agent with its
// identity/monitoring, the custom "NetOps Network Diagnostics Reader" role, and the read-only
// subscription RBAC the NetOps skills need. Phase 2 (plugin, subagent, scheduled tasks) runs
// against the agent data plane from deploy.sh -> install-api.sh.
//
// Least privilege (no write roles; Network Contributor is NOT required):
//   Reader, Monitoring Reader, Log Analytics Reader (built-in)
//   NetOps Network Diagnostics Reader (custom): only the POST-based read-only diagnostic actions
//   listed in skills/netops-managed-scope/readonly_guard.py DIAGNOSTIC_ACTIONS.
// Built-in role IDs: https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
// Custom role in Bicep: https://learn.microsoft.com/azure/role-based-access-control/custom-roles-bicep
// Action names: https://learn.microsoft.com/azure/role-based-access-control/permissions/networking
//               https://learn.microsoft.com/azure/network-watcher/required-rbac-permissions
//
//   az deployment sub create -l <region> -f main.bicep \
//     -p agentName=<name> resourceGroupName=<rg> location=<region> deployerObjectId=<oid>

targetScope = 'subscription'

@description('SRE Agent name.')
param agentName string = 'sre-netops-demo'

@description('Resource group for the agent (created if missing).')
param resourceGroupName string = 'SRE-NetOps-Demo'

@description('Azure region (must be an SRE Agent region, e.g. eastus2, centralus, swedencentral, uksouth, australiaeast).')
param location string = 'centralus'

@description('Object ID of the deploying identity (az ad signed-in-user show --query id -o tsv).')
param deployerObjectId string

@allowed(['User', 'ServicePrincipal', 'Group'])
param deployerPrincipalType string = 'User'

@description('Grant the agent identity Reader, Monitoring Reader, Log Analytics Reader and NetOps Network Diagnostics Reader on this subscription.')
param assignSubscriptionRoles bool = true

@description('Display name of the custom read-only diagnostics role.')
param diagnosticsRoleName string = 'NetOps Network Diagnostics Reader'

param tags object = {
  workload: 'netops-sre-agent'
}

var roles = [
  'acdd72a7-3385-48ef-bd42-f606fba81ae7' // Reader
  '43d0d8ad-25c7-4714-9337-8ba259a9fe05' // Monitoring Reader
  '73c42c96-874c-492b-b04d-ab87d138a893' // Log Analytics Reader
]

// Keep in sync with readonly_guard.DIAGNOSTIC_ACTIONS (enforced by tests/netops/test_deploy.py).
var diagnosticActions = [
  'Microsoft.Network/networkInterfaces/effectiveNetworkSecurityGroups/action'
  'Microsoft.Network/networkInterfaces/effectiveRouteTable/action'
  'Microsoft.Network/networkWatchers/ipFlowVerify/action'
  'Microsoft.Network/networkWatchers/nextHop/action'
  'Microsoft.Network/networkWatchers/securityGroupView/action'
  'Microsoft.Network/networkWatchers/topology/action'
  'Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action'
  'Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action'
  'Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action'
]

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

resource diagnosticsRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, diagnosticsRoleName)
  properties: {
    roleName: diagnosticsRoleName
    description: 'Read-only network diagnostics for the NetOps SRE Agent plugin: effective routes/NSGs, VPN/ExpressRoute BGP peer and route reads, and Network Watcher next hop / IP flow verify / topology. Grants no write actions.'
    type: 'customRole'
    permissions: [
      {
        actions: diagnosticActions
        notActions: []
      }
    ]
    assignableScopes: [
      subscription().id
    ]
  }
}

module agent 'agent.bicep' = {
  name: 'netops-sre-agent-${uniqueString(agentName)}'
  scope: rg
  params: {
    agentName: agentName
    location: location
    managedResources: [subscription().id]
    deployerObjectId: deployerObjectId
    deployerPrincipalType: deployerPrincipalType
    tags: tags
  }
}

resource subRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in roles: if (assignSubscriptionRoles) {
  name: guid(subscription().id, resourceGroupName, agentName, roleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    principalId: agent.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}]

resource diagRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignSubscriptionRoles) {
  name: guid(subscription().id, resourceGroupName, agentName, diagnosticsRole.id)
  properties: {
    roleDefinitionId: diagnosticsRole.id
    principalId: agent.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output agentId string = agent.outputs.agentId
output identityId string = agent.outputs.identityId
output identityPrincipalId string = agent.outputs.identityPrincipalId
output diagnosticsRoleId string = diagnosticsRole.id
output resourceGroupName string = rg.name
