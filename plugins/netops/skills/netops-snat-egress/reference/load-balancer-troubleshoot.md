# Skill: Load Balancer Troubleshooting (`lb_troubleshoot`)

Diagnose and resolve common load-balancer issues across Azure, AWS, and GCP. Covers HTTP errors (502, 504), SNAT exhaustion, backend health failures, asymmetric routing, TLS handshake failures, and per-cloud diagnostic commands.

---

## Issue 1: HTTP 502 Bad Gateway

The load balancer received an invalid response from the backend (or no response at all).

### Root Causes

| Cause | Cloud | Fix |
|---|---|---|
| Backend app crashed / not listening | All | Check app process, port binding, logs |
| Health probe passing but app partially broken | All | Improve health endpoint to check dependencies |
| Backend TLS mismatch (LB expects HTTPS, backend serves HTTP) | All | Align protocol settings |
| Connection timeout to backend | All | Check backend response time vs LB timeout |
| Backend security group/NSG blocking LB | All | Allow LB health-check source IPs |

### Diagnostic Commands

```bash
# Azure Application Gateway — backend health
az network application-gateway show-backend-health \
  --resource-group myRG \
  --name myAppGW \
  --query 'backendAddressPools[].backendHttpSettingsCollection[].servers[]' \
  --output table

# Azure — check AppGW diagnostic logs
az monitor diagnostic-settings list --resource myAppGW --resource-group myRG --resource-type Microsoft.Network/applicationGateways

# AWS ALB — check target health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,State:TargetHealth.State,Reason:TargetHealth.Reason}' \
  --output table

# GCP — check backend health
gcloud compute backend-services get-health my-backend-service --global \
  --format='table(status.healthStatus[].ipAddress, status.healthStatus[].healthState)'
```

---

## Issue 2: HTTP 504 Gateway Timeout

The backend did not respond within the LB's timeout window.

### Root Causes & Fixes

1. **Backend processing too slow** — optimize the backend query/response. Consider async patterns.
2. **LB timeout too low** — increase idle timeout.
3. **Keep-alive misconfiguration** — backend closing connections before LB expects.

```bash
# Azure LB — idle timeout (default 4 min, max 30 min)
az network lb rule update \
  --resource-group myRG --lb-name myLB --name myRule \
  --idle-timeout 10

# Azure AppGW — request timeout (default 20s, max 86400s)
az network application-gateway http-settings update \
  --resource-group myRG --gateway-name myAppGW --name mySettings \
  --timeout 60

# AWS ALB — idle timeout (default 60s)
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --attributes Key=idle_timeout.timeout_seconds,Value=120

# GCP — backend service timeout (default 30s)
gcloud compute backend-services update my-backend \
  --timeout=120 --global
```

---

## Issue 3: SNAT Exhaustion (Azure)

Azure Load Balancer Standard uses SNAT for outbound connections. When all SNAT ports are consumed, new outbound connections fail with connection timeouts.

### Symptoms

- Intermittent outbound connection failures from backend VMs.
- `SNAT port exhaustion` alerts in Azure Monitor.
- Works fine at low traffic, fails at scale.

### Diagnostic

```bash
# Check SNAT port allocation and usage
az monitor metrics list \
  --resource /subscriptions/.../Microsoft.Network/loadBalancers/myLB \
  --metric "SnatConnectionCount" \
  --aggregation Total \
  --interval PT1M \
  --output table

# Check used SNAT connections by state
az monitor metrics list \
  --resource /subscriptions/.../Microsoft.Network/loadBalancers/myLB \
  --metric "SnatConnectionCount" \
  --dimension ConnectionState \
  --aggregation Total
```

### Fixes

1. **Use NAT Gateway** (preferred) — provides 64K SNAT ports per public IP, dynamically allocated:
   ```bash
   az network nat gateway create --resource-group myRG --name myNATGW \
     --public-ip-addresses myNATGWPIP --idle-timeout 10
   az network vnet subnet update --resource-group myRG --vnet-name myVNet \
     --name backendSubnet --nat-gateway myNATGW
   ```
2. **Add outbound rules** with more frontend IPs (each IP adds ~64K ports).
3. **Reduce connection idle timeout** — release SNAT ports faster.
4. **Use connection pooling** — reuse HTTP connections instead of creating new ones per request.

---

## Issue 4: Backend Health Probe Failures

All backends showing unhealthy; no traffic served.

### Systematic Debug

```bash
# Step 1: Verify the app is running on the backend
curl -v http://localhost:8080/healthz   # from the backend VM itself

# Step 2: Verify NSG/firewall allows probe source IPs
# Azure LB probe source: 168.63.129.16
az network nsg rule list --resource-group myRG --nsg-name myNSG --output table

# AWS: ALB/NLB probes come from LB nodes within the VPC subnet
aws ec2 describe-security-groups --group-ids sg-... --query 'SecurityGroups[].IpPermissions'

# GCP: Health check source ranges: 35.191.0.0/16, 130.211.0.0/22
gcloud compute firewall-rules list --filter="name~health" --format=table

# Step 3: Verify probe port matches the app's listening port
# Step 4: For HTTPS probes, verify backend certificate is valid and trusted by the LB
# Step 5: Check probe timeout vs app response time
```

---

## Issue 5: Asymmetric Routing

Traffic enters through the LB but response packets take a different path (bypass the LB), causing connection drops.

### Common Scenarios

- **Azure**: VM has a public IP AND is behind a Load Balancer. Return traffic uses the VM's public IP instead of the LB's IP.
- **Multi-NIC VMs**: Response goes out a different NIC than the request came in on.
- **On-prem + LB**: UDR sends traffic to a firewall, but return traffic skips the firewall.

### Fixes

1. **Azure**: Remove public IPs from backend VMs if they're behind a LB. Use NAT Gateway or LB outbound rules for outbound connectivity.
2. **AWS**: Ensure route tables and security groups are symmetric. NLB uses DSR (Direct Server Return) by default — the source IP is the client IP, not the NLB IP.
3. **Use source NAT**: L7 LBs (ALB, AppGW) always SNAT — asymmetric routing is not an issue. L4 LBs may not SNAT.
4. **UDR symmetry**: Ensure both inbound and outbound paths traverse the same firewall/NVA.

---

## Issue 6: TLS Handshake Failures

Clients receive `ERR_SSL_PROTOCOL_ERROR` or `SSL_ERROR_HANDSHAKE_FAILURE_ALERT`.

### Diagnostic

```bash
# Test TLS handshake from client side
openssl s_client -connect myapp.contoso.com:443 -servername myapp.contoso.com -tls1_2

# Check certificate chain
openssl s_client -connect myapp.contoso.com:443 -showcerts

# Verify cipher suite compatibility
nmap --script ssl-enum-ciphers -p 443 myapp.contoso.com

# Azure AppGW — check SSL policy
az network application-gateway ssl-policy show --resource-group myRG --gateway-name myAppGW

# AWS ALB — check security policy
aws elbv2 describe-listeners --load-balancer-arn arn:... --query 'Listeners[].SslPolicy'
```

### Common Causes

1. **Certificate expired** — check `Not After` date in the cert.
2. **Hostname mismatch** — cert SAN doesn't match the FQDN.
3. **Missing intermediate certificate** — incomplete chain.
4. **TLS version mismatch** — client requires TLS 1.0 but LB enforces TLS 1.2+.
5. **Cipher mismatch** — client and LB share no common ciphers.
6. **SNI not sent** — old clients (Java 6, IE on XP) don't send SNI; LB can't select the right cert.

---

## Issue 7: Connection Draining / Deregistration Delays

Backend removed from pool but in-flight requests are dropped.

```bash
# Azure AppGW — connection draining (default: disabled)
az network application-gateway http-settings update \
  --resource-group myRG --gateway-name myAppGW --name mySettings \
  --connection-draining-enabled true --connection-draining-timeout 60

# AWS — deregistration delay (default: 300s)
aws elbv2 modify-target-group-attributes \
  --target-group-arn arn:... \
  --attributes Key=deregistration_delay.timeout_seconds,Value=60

# GCP — connection draining (default: 300s)
gcloud compute backend-services update my-backend \
  --connection-draining-timeout 60 --global
```

---

## Diagnostic Log Locations

| Cloud | Product | Logs Location |
|---|---|---|
| Azure | Application Gateway | Diagnostic settings → Log Analytics / Storage (AccessLog, FirewallLog) |
| Azure | Load Balancer | Azure Monitor Metrics (SnatConnectionCount, HealthProbeStatus) |
| Azure | Front Door | Diagnostic settings → FrontDoorAccessLog, FrontDoorHealthProbeLog |
| AWS | ALB/NLB | S3 bucket (access logs), CloudWatch (metrics) |
| AWS | WAF | CloudWatch Logs, S3, Kinesis Firehose |
| GCP | HTTP(S) LB | Cloud Logging (resource.type="http_load_balancer") |
| GCP | TCP/UDP LB | VPC Flow Logs for backend instances |

**Analysis only — verify against vendor documentation before applying.**
