# Skill: DNS Troubleshooting (`dns_troubleshoot`)

Diagnose and resolve DNS resolution failures across Azure, AWS, GCP, and hybrid environments. Covers nslookup/dig usage, forwarding chain tracing, private zone linking issues, stale cache, NXDOMAIN debugging, and common hybrid DNS pitfalls.

---

## Troubleshooting Methodology

Always follow this sequence:

1. **What is the FQDN that fails to resolve?**
2. **Where is the client?** (Azure VM, AWS EC2, on-prem server, laptop)
3. **What DNS server is the client using?** (cloud-provided, custom, on-prem)
4. **What response does the client get?** (NXDOMAIN, SERVFAIL, wrong IP, timeout)
5. **Trace the resolution chain** step by step from client → resolver → forwarder → authoritative.

---

## Essential Diagnostic Commands

### nslookup (Windows / Cross-Platform)

```powershell
# Basic query using default DNS server
nslookup myapp.contoso.com

# Query a specific DNS server
nslookup myapp.contoso.com 168.63.129.16

# Query for specific record type
nslookup -type=CNAME myapp.contoso.com
nslookup -type=MX contoso.com
nslookup -type=TXT contoso.com

# Reverse lookup
nslookup 10.0.1.4
```

### dig (Linux / macOS)

```bash
# Basic query with full detail
dig myapp.contoso.com

# Query specific server
dig @168.63.129.16 myapp.contoso.com

# Short output (just the answer)
dig +short myapp.contoso.com

# Trace the full resolution chain
dig +trace myapp.contoso.com

# Check specific record type
dig myapp.contoso.com CNAME
dig contoso.com MX
dig contoso.com TXT

# Reverse lookup
dig -x 10.0.1.4

# Check a specific nameserver with no recursion
dig @ns1-09.azure-dns.com myapp.contoso.com +norecurse

# Bypass cache — query authoritative directly
dig @ns1-09.azure-dns.com myapp.contoso.com +norec
```

### PowerShell (Windows)

```powershell
# Resolve DNS name
Resolve-DnsName -Name myapp.contoso.com -Type A
Resolve-DnsName -Name myapp.contoso.com -Server 168.63.129.16

# Clear local DNS cache
Clear-DnsClientCache

# View local DNS cache
Get-DnsClientCache | Where-Object { $_.Entry -like "*contoso*" }
```

---

## Issue 1: NXDOMAIN (Name Not Found)

The DNS server has no record for the queried name.

### Diagnostic Steps

```bash
# Step 1: Is the record actually in the zone?
az network dns record-set list --resource-group myRG --zone-name contoso.com \
  --query '[?name==`myapp`]' --output table

# Step 2: Is the zone linked to the VNet? (private zone)
az network private-dns link vnet list --resource-group myRG \
  --zone-name internal.contoso.com --output table

# Step 3: Is the client using the right DNS server?
# From the Azure VM:
cat /etc/resolv.conf   # Linux
ipconfig /all           # Windows — check "DNS Servers" field

# Step 4: Can the Azure-provided DNS resolve it?
dig @168.63.129.16 myapp.internal.contoso.com

# Step 5: Is there a forwarding rule intercepting the query?
az dns-resolver forwarding-rule list --resource-group myRG --ruleset-name myRuleset --output table
```

### Common Causes

| Cause | Fix |
|---|---|
| Record does not exist in the zone | Create the A/CNAME record |
| Private zone not linked to the VNet | Create a VNet link |
| Forwarding rule sending query to wrong DNS server | Fix the target DNS server IP in the forwarding rule |
| Split-horizon: public zone exists but private zone is missing | Create the private zone with the internal record |
| Zone delegation broken: NS records in parent zone are wrong | Update NS delegation at registrar or parent zone |

---

## Issue 2: Resolves to Public IP Instead of Private IP

This is the **#1 private endpoint DNS issue**. The FQDN resolves to the public IP even though a private endpoint exists.

### Root Cause

The `privatelink.*` DNS zone is either missing, not linked to the VNet, or the A record for the PE was not created.

### Diagnostic

```bash
# Expected resolution chain:
# mystorageaccount.blob.core.windows.net
#   → CNAME → mystorageaccount.privatelink.blob.core.windows.net
#   → A → 10.0.1.4 (private IP)

# Actual (broken) resolution:
nslookup mystorageaccount.blob.core.windows.net
# Returns: 52.239.xxx.xxx (public IP) — the privatelink CNAME is not being resolved

# Check: Does the privatelink zone exist?
az network private-dns zone show --resource-group myRG \
  --name privatelink.blob.core.windows.net 2>/dev/null || echo "ZONE MISSING"

# Check: Is the zone linked to the VNet?
az network private-dns link vnet list --resource-group myRG \
  --zone-name privatelink.blob.core.windows.net --output table

# Check: Does the A record exist in the zone?
az network private-dns record-set a list --resource-group myRG \
  --zone-name privatelink.blob.core.windows.net \
  --query '[?name==`mystorageaccount`]' --output table
```

### Fix

```bash
# Create the private DNS zone if missing
az network private-dns zone create --resource-group myRG \
  --name privatelink.blob.core.windows.net

# Link to VNet
az network private-dns link vnet create --resource-group myRG \
  --zone-name privatelink.blob.core.windows.net \
  --name myLink --virtual-network myVNet --registration-enabled false

# Create A record for the PE (or use Azure Policy for automation)
az network private-dns record-set a add-record --resource-group myRG \
  --zone-name privatelink.blob.core.windows.net \
  --record-set-name mystorageaccount --ipv4-address 10.0.1.4
```

---

## Issue 3: On-Prem Cannot Resolve Azure Private DNS

On-premises clients resolve Azure private zone names as NXDOMAIN because the on-prem DNS has no forwarder pointing at Azure.

### Diagnostic

```powershell
# From on-prem server
nslookup myvm.internal.contoso.com    # NXDOMAIN
nslookup myvm.internal.contoso.com 10.0.0.4    # Works (10.0.0.4 = Azure DNS Private Resolver inbound EP)
```

### Fix

1. Ensure Azure DNS Private Resolver has an **inbound endpoint** deployed.
2. On on-prem DNS (AD), add a **conditional forwarder** for the Azure private zone pointing at the inbound endpoint IP.
3. Ensure network connectivity (VPN/ER) allows UDP/TCP 53 from on-prem DNS to the inbound endpoint IP.
4. For private endpoints, also add conditional forwarders for all `privatelink.*` zones.

---

## Issue 4: Forwarding Chain Failures

DNS queries forwarded between resolvers can fail at any hop.

### Trace the Chain

```bash
# Azure VM → Azure DNS (168.63.129.16) → Outbound EP → On-prem DNS
# Test each hop:

# Hop 1: Azure VM → Azure DNS
dig @168.63.129.16 dc01.corp.contoso.com

# Hop 2: Does the forwarding rule exist?
az dns-resolver forwarding-rule list --resource-group myRG --ruleset-name myRuleset \
  --query "[?domainName=='corp.contoso.com.']" --output table

# Hop 3: Is the on-prem DNS reachable from Azure?
# From a VM in the outbound endpoint's VNet:
nc -zv 10.100.0.10 53    # Test TCP 53
dig @10.100.0.10 dc01.corp.contoso.com   # Test actual resolution
```

### Common Causes

| Cause | Fix |
|---|---|
| Forwarding ruleset not linked to the VNet | Link the ruleset to the VNet |
| Target DNS IP unreachable (firewall, routing) | Check NSG, UDR, VPN gateway routing |
| Target DNS server not authoritative for the zone | Fix the forwarding rule target IPs |
| DNS query too large for UDP (truncated) | Ensure TCP 53 is also allowed |

---

## Issue 5: Stale DNS Cache

Client resolves a stale/old IP after a record change.

```bash
# Check TTL of cached response
dig myapp.contoso.com | grep -i ttl

# Remaining cache time = TTL value in response
# Wait for TTL to expire, or flush cache:

# Windows client
ipconfig /flushdns

# Linux (systemd-resolved)
sudo systemd-resolve --flush-caches

# macOS
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder

# Upstream resolver caches (8.8.8.8, 1.1.1.1) cannot be flushed — must wait for TTL
```

---

## DNS Troubleshooting Decision Tree

```
Query fails (NXDOMAIN / timeout / wrong IP)
├── Is the record in the zone? → No → Create it
├── Is the zone linked to the VNet/VPC? → No → Link it
├── Is the client using the right DNS server? → No → Fix DHCP/VNet DNS settings
├── Is there a forwarding rule? → Check if it forwards to the right target
├── Is the target DNS reachable? → No → Check network (VPN, NSG, firewall)
├── Is it a privatelink issue? → Check privatelink zone + VNet link + A record
└── Is it a cache issue? → Flush cache, wait for TTL
```

**Analysis only — verify against vendor documentation before applying.**
