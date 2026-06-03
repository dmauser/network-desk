# Skill: Private Endpoint Security Review (`pl_security_review`)

Review and harden private endpoint security posture. Covers NSG support on PE subnets, network policies, UDR support, disabling public access, and network policy configuration across Azure, AWS, and GCP.

---

## Azure Private Endpoint Network Policies

Historically, Azure private endpoints did **not** support NSGs or UDRs on their subnets. This has changed — network policies can now be enabled.

### Enabling Network Policies

```bash
# Enable network policies on the PE subnet (required for NSG/UDR to apply to PE traffic)
az network vnet subnet update \
  --resource-group myRG \
  --vnet-name myVNet \
  --name PrivateEndpointSubnet \
  --private-endpoint-network-policies Enabled

# Verify the setting
az network vnet subnet show \
  --resource-group myRG \
  --vnet-name myVNet \
  --name PrivateEndpointSubnet \
  --query 'privateEndpointNetworkPolicies'
```

**Network policy states:**
- `Disabled` (legacy default): NSG and UDR rules are **ignored** for PE traffic on this subnet.
- `Enabled`: NSG and UDR rules **apply** to PE traffic.
- `NetworkSecurityGroupEnabled`: Only NSG rules apply (UDR bypassed).
- `RouteTableEnabled`: Only UDR rules apply (NSG bypassed).

### NSG Rules for Private Endpoints

Once network policies are enabled, apply NSGs to control which sources can reach PEs:

```bash
# Allow only specific workload subnet to reach PE subnet
az network nsg rule create \
  --resource-group myRG \
  --nsg-name peSubnetNSG \
  --name AllowWorkloadToStorage \
  --priority 100 \
  --direction Inbound \
  --source-address-prefixes 10.1.0.0/24 \
  --destination-address-prefixes 10.0.4.0/24 \
  --destination-port-ranges 443 \
  --protocol Tcp \
  --access Allow

# Deny all other inbound traffic to PE subnet
az network nsg rule create \
  --resource-group myRG \
  --nsg-name peSubnetNSG \
  --name DenyAllInbound \
  --priority 4096 \
  --direction Inbound \
  --source-address-prefixes "*" \
  --destination-address-prefixes "*" \
  --destination-port-ranges "*" \
  --protocol "*" \
  --access Deny
```

### UDR for Private Endpoints

Force PE traffic through Azure Firewall or NVA:

```bash
# Route PE-destined traffic through firewall
az network route-table route create \
  --resource-group myRG \
  --route-table-name workloadRT \
  --name toPE \
  --address-prefix 10.0.4.0/24 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address 10.0.1.4
```

---

## Disabling Public Access

**Creating a private endpoint does NOT disable public access.** This is the most misunderstood aspect of private endpoints. You must explicitly disable public access on the PaaS resource.

### Azure

```bash
# Storage Account — disable public access
az storage account update \
  --resource-group myRG --name mystorageaccount \
  --public-network-access Disabled

# Azure SQL — disable public access
az sql server update \
  --resource-group myRG --name mysqlserver \
  --public-network-access Disabled

# Key Vault — disable public access
az keyvault update \
  --resource-group myRG --name mykeyvault \
  --public-network-access Disabled

# Cosmos DB — disable public access
az cosmosdb update \
  --resource-group myRG --name mycosmosdb \
  --public-network-access Disabled
```

### AWS

AWS services use **resource policies** and **endpoint policies** to restrict access:

```bash
# S3 bucket policy — restrict to VPC endpoint only
aws s3api put-bucket-policy --bucket my-bucket --policy '{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "RestrictToVPCe",
    "Effect": "Deny",
    "Principal": "*",
    "Action": "s3:*",
    "Resource": ["arn:aws:s3:::my-bucket", "arn:aws:s3:::my-bucket/*"],
    "Condition": {
      "StringNotEquals": {
        "aws:sourceVpce": "vpce-0123456789abcdef0"
      }
    }
  }]
}'

# VPC endpoint policy — restrict which S3 buckets are accessible
aws ec2 modify-vpc-endpoint --vpc-endpoint-id vpce-... --policy-document '{
  "Statement": [{
    "Sid": "AllowSpecificBucket",
    "Effect": "Allow",
    "Principal": "*",
    "Action": ["s3:GetObject", "s3:PutObject"],
    "Resource": "arn:aws:s3:::my-bucket/*"
  }]
}'
```

### GCP

```bash
# Use VPC Service Controls to restrict access to PaaS services
gcloud access-context-manager perimeters create my-perimeter \
  --title="Production Perimeter" \
  --resources="projects/12345" \
  --restricted-services="storage.googleapis.com,bigquery.googleapis.com" \
  --access-levels="accessPolicies/.../accessLevels/corp-network"
```

---

## Security Review Checklist

| Check | Status | Command to Verify |
|---|---|---|
| PE network policies enabled on subnet | ☐ | `az network vnet subnet show ... --query privateEndpointNetworkPolicies` |
| NSG applied to PE subnet | ☐ | `az network vnet subnet show ... --query networkSecurityGroup.id` |
| Public access disabled on PaaS resource | ☐ | `az storage account show ... --query publicNetworkAccess` |
| PE connection state is `Approved` | ☐ | `az network private-endpoint show ... --query privateLinkServiceConnections[0].privateLinkServiceConnectionState.status` |
| DNS resolves to private IP (not public) | ☐ | `nslookup <fqdn>` |
| No service firewall exceptions allowing public IPs | ☐ | `az storage account network-rule list ...` |
| PE activity logging enabled | ☐ | Use VNet flow logs for new Azure deployments; keep NSG flow logs only for legacy migration and verify lifecycle dates: https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| AWS endpoint policy restricts access | ☐ | `aws ec2 describe-vpc-endpoints --query 'VpcEndpoints[].PolicyDocument'` |
| AWS resource policy restricts to VPCe | ☐ | Check S3/SQS/SNS resource policies |
| GCP VPC Service Controls configured | ☐ | `gcloud access-context-manager perimeters list` |

---

## Common Security Mistakes

1. **Assuming PE = no public access** — PE only adds a private path; it doesn't remove the public one.
2. **NSGs not applied because network policies are disabled** — enable `privateEndpointNetworkPolicies` on the subnet first.
3. **Overly permissive VPC endpoint policies (AWS)** — default endpoint policy allows all actions to all resources. Scope it down.
4. **No logging** — enable VNet flow logs for new Azure deployments and VPC flow logs for AWS/GCP; use NSG flow logs only for legacy migration after checking the Azure lifecycle notice.
5. **Service firewall exceptions left open** — after enabling PE, remove any "Allow all networks" or specific public IP rules from the service firewall.

**Analysis only — verify against vendor documentation before applying.**
