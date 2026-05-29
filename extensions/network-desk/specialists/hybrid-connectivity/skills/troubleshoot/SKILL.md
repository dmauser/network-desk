# Skill: Hybrid Connectivity Troubleshooting (hyb_troubleshoot)

Diagnose and resolve hybrid connectivity issues including BGP neighbor problems, tunnel failures, MTU issues, asymmetric routing, and IKE mismatches. This skill provides systematic diagnostic procedures with real CLI commands for each cloud provider.

---

## BGP Neighbor State Machine Issues

BGP establishes a peering session through six states. Failures at each state indicate specific problems:

### State Machine: Idle → Connect → Active → OpenSent → OpenConfirm → Established

**Idle**: Initial state. Router has a BGP neighbor configured but no TCP connection attempted (or previous attempt failed and waiting for retry). If stuck in Idle, check:
- Neighbor IP reachability: `ping <neighbor-ip>` from the interface used for BGP.
- Route to neighbor exists: `show ip route <neighbor-ip>`.
- BGP process is running: `show ip bgp summary`.
- No administrative shutdown: `show run | section router bgp`.

**Connect**: TCP SYN sent to neighbor on port 179. If stuck or cycling between Connect and Active:
- Firewall blocking TCP 179 — check NSG/SG rules and on-premises firewall.
- ACL on the peering interface filtering BGP traffic.
- Incorrect neighbor IP address (off by one, wrong peering subnet).

**Active**: TCP connection failed; retrying. Common cause of Idle/Active cycling:
- Asymmetric peering IPs (local router uses IP A, remote expects IP B).
- Multi-hop BGP without `ebgp-multihop` or `ttl-security` configured.
- Source interface mismatch: `neighbor <ip> update-source <interface>` needed.

**OpenSent**: TCP connected, BGP OPEN message sent. Stuck here indicates:
- AS number mismatch: local router's configured remote AS doesn't match the neighbor's actual AS.
- BGP version mismatch (rare — both sides should be BGP-4).
- Hold time negotiation failure.

**OpenConfirm**: OPEN message received and validated, waiting for KEEPALIVE. Stuck here indicates:
- MD5 authentication key mismatch: both sides must use identical keys.
- BGP router-id conflict (two routers with the same router-id).

**Established**: Peering is up. Routes are exchanged. If routes are not appearing:
- No routes matching outbound route-map/prefix-list being advertised.
- Maximum prefix limit reached — session may be torn down.
- Address family mismatch (IPv4 unicast not activated under the neighbor).

### Diagnostic Commands
```bash
# Cisco IOS/IOS-XE
show ip bgp summary
show ip bgp neighbors <ip>
show ip bgp neighbors <ip> received-routes
show ip bgp neighbors <ip> advertised-routes
debug ip bgp events         # caution: verbose in production

# Azure ExpressRoute BGP
az network vnet-gateway list-bgp-peer-status \
  --resource-group MyRG --name MyERGateway

# AWS Direct Connect BGP
aws directconnect describe-virtual-interfaces \
  --virtual-interface-id dxvif-xxxx
# Check bgpPeers[].bgpStatus — should be "up"

# GCP Cloud Router BGP
gcloud compute routers get-status my-cloud-router --region us-central1
# Check bgpPeerStatus[].status — should be "UP"
```

---

## Tunnel Up But No Traffic

The VPN tunnel shows "Connected" status, but no data flows through. This is one of the most common hybrid connectivity issues.

### Diagnostic Checklist
1. **Verify traffic selectors / proxy IDs**: Phase 2 traffic selectors must match on both sides. Azure uses 0.0.0.0/0 ↔ 0.0.0.0/0 for route-based VPN; policy-based VPN uses specific subnets. Mismatch causes traffic to be encrypted but not decrypted by the peer.

2. **Check routing**: Traffic must have a route pointing to the VPN tunnel interface.
   ```bash
   # Azure — check effective routes on VM NIC
   az network nic show-effective-route-table \
     --resource-group MyRG --name MyVMNic
   # Look for routes with nextHopType "VirtualNetworkGateway"
   ```

3. **Verify NSG rules**: NSGs may block traffic even after it traverses the tunnel.
   ```bash
   az network watcher test-ip-flow \
     --direction Inbound --protocol TCP \
     --local 10.1.0.4:443 --remote 192.168.1.100:12345 \
     --vm MyVM --nic MyVMNic --resource-group MyRG
   ```

4. **Check on-premises firewall**: Post-decryption traffic must be allowed by the on-premises firewall. Many firewalls require explicit rules for traffic arriving on VPN tunnel interfaces.

5. **Validate BGP route exchange** (if using BGP): Ensure routes are learned and installed.

---

## MTU / MSS Issues Over VPN

### The Problem
IPsec encapsulation adds 50–73 bytes of overhead per packet. If the original packet is 1500 bytes (standard Ethernet MTU), the encapsulated packet becomes 1550–1573 bytes, exceeding the path MTU and causing fragmentation or drops.

### Common MTU Values
| Path | MTU |
|------|-----|
| Standard Ethernet | 1500 bytes |
| IPsec VPN tunnel | 1400 bytes (typical effective) |
| GRE + IPsec | 1360 bytes |
| Azure VNet (intra-VNet) | 1500 bytes |
| Azure accelerated networking | 8900 bytes (jumbo frames within VNet) |
| AWS VPC | 9001 bytes (jumbo frames within VPC) |

### MSS Clamping
Set TCP Maximum Segment Size (MSS) to prevent fragmentation. MSS = MTU - 40 bytes (IP + TCP headers).
```
# On-premises router — clamp MSS on VPN tunnel interface
interface Tunnel0
  ip tcp adjust-mss 1360
```

### Diagnosing MTU Issues
Symptoms: large file transfers fail, SSH works but SCP/SFTP stalls, web pages partially load.
```bash
# Test with DF bit set (don't fragment) — find the largest working packet
# Linux
ping -M do -s 1400 <destination>    # Decrease size until it works
# Windows
ping -f -l 1400 <destination>
```

---

## Asymmetric Routing

Traffic from source to destination takes a different path than return traffic. Problematic when stateful devices (firewalls, NAT, load balancers) are in the path — they may drop return traffic because they have no session state for it.

### Common Causes
- Multiple VPN tunnels or ExpressRoute circuits without consistent routing policy.
- On-premises traffic exits via Circuit A, but Azure return traffic comes back via Circuit B (different BGP attributes on each path direction).
- UDR in Azure pointing to NVA for one direction but not the other.

### Resolution
- Ensure BGP attributes are symmetric: if LP prefers Circuit A for outbound, use AS-path prepending or MED to also prefer Circuit A for inbound.
- On stateful firewalls, ensure both directions of a flow traverse the same firewall instance (or use session synchronization between HA pairs).
- Use Azure Route Server to inject routes consistently across all NVA instances.

---

## IKE Phase 1 / Phase 2 Mismatch

### Phase 1 (IKE SA) Mismatch Symptoms
- Tunnel status shows "Connecting" or "Not Connected".
- Logs show: "No proposal chosen" or "INVALID_KE_PAYLOAD".

**Common mismatches**: Encryption algorithm (AES-256 vs AES-128), integrity algorithm (SHA-256 vs SHA-1), DH group (Group 14 vs Group 2), authentication method (PSK vs certificate), IKE version (IKEv1 vs IKEv2).

### Phase 2 (IPsec SA) Mismatch Symptoms
- IKE SA establishes (Phase 1 succeeds), but no IPsec SA forms.
- Logs show: "No proposal chosen" for Quick Mode / CREATE_CHILD_SA.

**Common mismatches**: ESP encryption algorithm, ESP integrity algorithm, PFS group, traffic selectors (proxy IDs).

### Diagnostic Commands
```bash
# Cisco IOS — show IKE/IPsec SAs
show crypto isakmp sa
show crypto ipsec sa
debug crypto isakmp
debug crypto ipsec

# Azure VPN Gateway diagnostics
az network vpn-connection show \
  --name MyConnection --resource-group MyRG \
  --query '{status:connectionStatus, ike:ipsecPolicies}'

# AWS VPN tunnel status
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-xxxx \
  --query 'VpnConnections[0].VgwTelemetry'
```

---

## Route Not Advertised

### From On-Premises to Cloud
1. Verify the route exists in the local BGP table: `show ip bgp <prefix>`.
2. Check outbound route-map/prefix-list: `show ip bgp neighbors <ip> advertised-routes`.
3. Verify the route is not filtered by a `distribute-list`, `prefix-list`, or `route-map` applied to the neighbor.
4. Check maximum prefix limit on the cloud side — if exceeded, the session may have been torn down.

### From Cloud to On-Premises
1. Check the VNet/VPC address space is correctly configured.
2. Verify peering/connection has route propagation enabled.
3. Check cloud-side route filters (ExpressRoute route filters for Microsoft peering, AWS VIF prefix limits).
4. Verify BGP session is Established: use cloud CLI to check peer status.

```bash
# Azure — check learned routes from ExpressRoute
az network vnet-gateway list-learned-routes \
  --resource-group MyRG --name MyERGateway

# Azure — check advertised routes to peer
az network vnet-gateway list-advertised-routes \
  --resource-group MyRG --name MyERGateway --peer 10.0.0.1

# AWS — check routes learned via Direct Connect
aws ec2 describe-route-tables --route-table-id rtb-xxxx \
  --query 'RouteTables[0].Routes[?Origin==`EnableVgwRoutePropagation`]'

# GCP — check Cloud Router learned/advertised routes
gcloud compute routers get-status my-router --region us-central1
```

**Analysis only — verify against vendor documentation before applying.**
