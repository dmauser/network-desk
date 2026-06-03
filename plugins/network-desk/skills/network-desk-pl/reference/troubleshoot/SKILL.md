# Skill: Private Endpoint Troubleshooting (`pl_troubleshoot`)

Diagnose and resolve private endpoint connectivity failures across Azure, AWS, and GCP. The most common issues are DNS-related, but also covers approval state, NSG blocking, connection state, and cross-region access problems.

---

## Troubleshooting Methodology

Follow this order — **DNS first, always:**

```
PE connectivity fails
├── Step 1: DNS — does the FQDN resolve to the private IP?
├── Step 2: Connection state — is the PE approved and connected?
├── Step 3: Network — is the path open (NSG, firewall, routing)?
├── Step 4: Service — is the PaaS resource configured correctly?
└── Step 5: Client — is the client configured to use the right endpoint?
```

---

## Issue 1: DNS Resolves to Public IP Instead of Private IP

**This is the #1 private endpoint issue — responsible for ~80% of PE failures.**

### Symptoms

```
nslookup mystorageaccount.blob.core.windows.net
  → Address: 52.239.xxx.xxx (PUBLIC IP — WRONG)

Expected:
  → CNAME: mystorageaccount.privatelink.blob.core.windows.net
  → Address: 10.0.1.4 (PRIVATE IP — CORRECT)
```

### Diagnostic Workflow

```bash
# Step 1: Check if the privatelink CNAME exists (Azure adds this automatically)
dig mystorageaccount.blob.core.windows.net CNAME +short
# Expected: mystorageaccount.privatelink.blob.core.windows.net
# If missing: PE may not be properly created

# Step 2: Check if the private DNS zone exists
az network private-dns zone show \
  --resource-group dns-rg \
  --name privatelink.blob.core.windows.net \
  2>/dev/null && echo "ZONE EXISTS" || echo "ZONE MISSING"

# Step 3: Check if the zone is linked to the VNet
az network private-dns link vnet list \
  --resource-group dns-rg \
  --zone-name privatelink.blob.core.windows.net \
  --output table

# Step 4: Check if the A record exists in the zone
az network private-dns record-set a list \
  --resource-group dns-rg \
  --zone-name privatelink.blob.core.windows.net \
  --query "[?name=='mystorageaccount']" \
  --output table

# Step 5: Check DNS zone group on the PE (auto-creates A records)
az network private-endpoint dns-zone-group list \
  --resource-group myRG \
  --endpoint-name myBlobPE \
  --output table

# Step 6: If using custom DNS, verify it forwards privatelink queries to 168.63.129.16
# From the custom DNS server:
nslookup mystorageaccount.privatelink.blob.core.windows.net 168.63.129.16
```

### Fix Matrix

| Root Cause | Fix |
|---|---|
| Private DNS zone doesn't exist | Create the zone: `az network private-dns zone create ...` |
| Zone not linked to VNet | Create VNet link: `az network private-dns link vnet create ...` |
| A record missing in zone | Create DNS zone group on PE or add A record manually |
| Custom DNS not forwarding | Add conditional forwarder for `privatelink.*` → 168.63.129.16 |
| Resolving from outside Azure | On-prem: add conditional forwarder → DNS Private Resolver inbound EP |
| Stale DNS cache | Flush client cache: `ipconfig /flushdns` or `systemd-resolve --flush-caches` |

---

## Issue 2: PE Connection State — Pending or Rejected

### Diagnostic

```bash
# Azure — check PE connection state
az network private-endpoint show \
  --resource-group myRG \
  --name myPE \
  --query 'privateLinkServiceConnections[0].privateLinkServiceConnectionState' \
  --output json

# Expected: { "status": "Approved", "description": "...", "actionsRequired": "None" }
# Problem states: "Pending", "Rejected", "Disconnected"

# AWS — check VPC endpoint state
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-... \
  --query 'VpcEndpoints[].{State:State,DNS:DnsEntries[0].DnsName}'

# GCP — check PSC connection status
gcloud compute forwarding-rules describe my-psc-endpoint --region=us-central1 \
  --format='get(pscConnectionStatus)'
```

### Fix

| State | Cause | Fix |
|---|---|---|
| **Pending** | Manual approval required | Approve: `az network private-endpoint-connection approve ...` |
| **Rejected** | Provider rejected the connection | Contact the service provider; re-create the PE if needed |
| **Disconnected** | PE was approved then disconnected (PaaS resource moved/deleted) | Recreate PE and DNS records |
| **pendingAcceptance** (AWS) | `acceptance-required` is true on the service | Accept: `aws ec2 accept-vpc-endpoint-connections ...` |
| **rejected** (AWS) | Provider rejected | Contact provider; recreate endpoint |

---

## Issue 3: NSG Blocking PE Traffic

### Symptoms

DNS resolves correctly to private IP, but connections timeout or are refused.

### Diagnostic

```bash
# Step 1: Check if network policies are enabled on PE subnet
az network vnet subnet show \
  --resource-group myRG --vnet-name myVNet --name peSubnet \
  --query 'privateEndpointNetworkPolicies'
# If "Enabled", NSG rules ARE applied to PE traffic

# Step 2: Check NSG rules on PE subnet
az network nsg rule list --resource-group myRG --nsg-name peSubnetNSG --output table

# Step 3: Check NSG flow logs for denied traffic
# Look for traffic from source workload IP to PE IP on port 443

# Step 4: Check NSG on source subnet (outbound rules)
az network nsg rule list --resource-group myRG --nsg-name workloadSubnetNSG \
  --query "[?direction=='Outbound']" --output table

# AWS — check security group on interface endpoint
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-... \
  --query 'VpcEndpoints[].Groups'

aws ec2 describe-security-groups --group-ids sg-... \
  --query 'SecurityGroups[].IpPermissions'
```

### Fix

```bash
# Azure — ensure NSG allows traffic from workload to PE on 443
az network nsg rule create \
  --resource-group myRG --nsg-name peSubnetNSG \
  --name AllowHTTPS --priority 100 --direction Inbound \
  --source-address-prefixes 10.1.0.0/24 \
  --destination-port-ranges 443 --protocol Tcp --access Allow

# AWS — update security group on endpoint
aws ec2 authorize-security-group-ingress \
  --group-id sg-endpoint \
  --protocol tcp --port 443 \
  --source-group sg-workload
```

---

## Issue 4: Cross-Region or Cross-VNet Access

### Azure

Private endpoints are **regional**. A PE in East US cannot be directly accessed from a workload in West Europe unless:

1. **VNet peering** is established between the two VNets (same or different regions).
2. The private DNS zone is linked to **both** VNets.

```bash
# Verify VNet peering exists
az network vnet peering list --resource-group myRG --vnet-name spoke1VNet --output table

# Verify DNS zone linked to both VNets
az network private-dns link vnet list --resource-group dns-rg \
  --zone-name privatelink.blob.core.windows.net --output table
```

### AWS

Interface endpoints are **per-VPC, per-AZ**. Cross-VPC access requires:

1. VPC peering or Transit Gateway.
2. DNS resolution via shared Route 53 private hosted zones.

### GCP

PSC endpoints are **regional**. Cross-region requires:

1. Deploy separate PSC endpoints in each region, OR
2. Use Internal TCP Proxy LB for cross-region routing.

---

## Issue 5: Application-Level Errors After Enabling PE

### Symptoms

DNS resolves correctly, TCP connection succeeds, but the application returns errors (403 Forbidden, authentication failures).

### Common Causes

| Cause | Fix |
|---|---|
| **Service firewall blocks private IP range** | Add PE subnet to the service's network rules: `az storage account network-rule add --ip-address 10.0.4.0/24` |
| **Managed identity not authorized** | PE changes the source IP; if the service uses IP-based access control, update the allowed IPs |
| **Connection string still using public endpoint** | Update connection string if the service uses a different FQDN for private access |
| **Key Vault access policy missing** | For Key Vault with RBAC: ensure the calling identity has the right role |
| **Storage account requires SAS/key but PE doesn't change auth** | PE affects network path only, not authentication |

### Quick Connectivity Test

```bash
# Azure — test from workload VM
curl -v https://mystorageaccount.blob.core.windows.net/ 2>&1 | head -20

# Check the resolved IP in the curl output
# If the IP is 10.x.x.x → PE path is used
# If the IP is 52.x.x.x → public path is used

# AWS — test from EC2
curl -v https://sqs.us-east-1.amazonaws.com/ 2>&1 | head -20

# GCP — test from VM
curl -v https://storage.googleapis.com/my-bucket/test.txt 2>&1 | head -20
```

---

## Diagnostic Command Quick Reference

| Task | Azure | AWS | GCP |
|---|---|---|---|
| Check PE state | `az network private-endpoint show ...` | `aws ec2 describe-vpc-endpoints ...` | `gcloud compute forwarding-rules describe ...` |
| Check DNS | `nslookup <fqdn> 168.63.129.16` | `dig <fqdn> @169.254.169.253` | `dig <fqdn> @169.254.169.254` |
| Check PE IP | `az network private-endpoint show --query 'networkInterfaces[0].id'` → `az network nic show --query 'ipConfigurations[0].privateIPAddress'` | `aws ec2 describe-vpc-endpoints --query 'VpcEndpoints[].NetworkInterfaceIds'` → `aws ec2 describe-network-interfaces` | `gcloud compute addresses describe my-psc-ip --format='get(address)'` |
| Check DNS zone links | `az network private-dns link vnet list ...` | `aws route53 list-hosted-zones-by-vpc ...` | `gcloud dns managed-zones list --filter="visibility=private"` |
| Check NSG/SG | `az network nsg rule list ...` | `aws ec2 describe-security-groups ...` | `gcloud compute firewall-rules list ...` |

**Analysis only — verify against vendor documentation before applying.**
