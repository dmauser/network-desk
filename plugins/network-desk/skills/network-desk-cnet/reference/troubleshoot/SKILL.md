# Skill: Container Networking Troubleshooting

## Purpose

Provide systematic methodologies for diagnosing and resolving container networking issues in Kubernetes clusters. Covers pod-to-pod connectivity, DNS resolution, CNI failures, network policy debugging, service mesh issues, and the tooling required for effective troubleshooting.

## Core Knowledge

### Troubleshooting Framework

Follow this systematic approach for any container networking issue:

1. **Identify the scope** — Is it one pod, one node, one namespace, or cluster-wide?
2. **Check basic connectivity** — Can the pod reach its own node? Other pods on same node? Pods on other nodes?
3. **Verify DNS** — Is name resolution working? Can the pod resolve cluster services and external names?
4. **Inspect network policies** — Are there policies that could be blocking traffic?
5. **Examine CNI** — Is the CNI plugin healthy? Are pod IPs properly assigned?
6. **Check service mesh** — If present, is the sidecar injected and healthy?
7. **Validate infrastructure** — Are cloud-level network controls (NSGs, security groups) allowing traffic?

### Pod-to-Pod Connectivity Issues

#### Diagnostic Steps

```bash
# Step 1: Verify pod status and IP assignment
kubectl get pod -o wide -n production
# Check: Is the pod Running? Does it have an IP?

# Step 2: Check events for network-related errors
kubectl describe pod <pod-name> -n production
# Look for: CNI errors, IP allocation failures, sandbox creation errors

# Step 3: Test connectivity from the pod
kubectl exec -it <pod-name> -n production -- sh
# Inside pod:
ping <target-pod-ip>           # L3 connectivity
curl -v <target-pod-ip>:8080   # L4 connectivity
wget -O- <service-name>:8080   # Service resolution + connectivity

# Step 4: Test from another pod on same node vs different node
# This isolates whether the issue is intra-node or inter-node
kubectl get pods -o wide | grep <node-name>

# Step 5: Test from host network
kubectl run nettest --rm -it --image=nicolaka/netshoot \
  --overrides='{"spec":{"hostNetwork":true,"nodeName":"node-1"}}' -- bash
```

#### Common Causes and Fixes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|------------|-----|
| Pod can't reach pods on other nodes | CNI overlay broken, MTU mismatch | `traceroute`, check MTU | Restart CNI pods, fix MTU config |
| Pod can't reach pods on same node | veth pair issue, bridge problem | `ip link show`, `brctl show` | Delete and recreate pod |
| Intermittent connectivity | SNAT port exhaustion, conntrack table full | `conntrack -S`, `dmesg` | Increase conntrack max, add SNAT IPs |
| Connection timeouts | Cloud NSG/SG blocking, asymmetric routing | Check cloud firewall rules | Update NSG/SG rules |
| TCP resets | Network policy deny, service port mismatch | `tcpdump`, policy audit | Fix policy or service port mapping |

#### MTU Issues

MTU mismatches are a common source of silent failures (small packets work, large ones fail):

```bash
# Check MTU at various points
kubectl exec <pod> -- ip link show eth0       # Pod interface MTU
kubectl exec <pod> -- cat /sys/class/net/eth0/mtu

# Test path MTU
kubectl exec <pod> -- ping -M do -s 1400 <target-ip>
# Reduce size until it works to find effective MTU

# Common MTU considerations:
# Azure VNet / Azure CNI Overlay: do not assume encapsulation overhead; verify pod and node MTU from the running cluster
# AWS VPC CNI: often supports jumbo frames in VPC, but verify instance/path MTU
# Calico VXLAN: commonly 1450 when VXLAN encapsulation is enabled
# Cilium Geneve/VXLAN: commonly 1450 when encapsulation is enabled
# WireGuard: commonly 1420 (1500 - 80 WireGuard overhead)
```

### DNS Resolution (CoreDNS) Debugging

DNS issues are the most common cause of service connectivity failures in Kubernetes.

#### Diagnostic Steps

```bash
# Step 1: Test DNS from inside a pod
kubectl exec -it <pod> -- nslookup kubernetes.default.svc.cluster.local
kubectl exec -it <pod> -- nslookup <service-name>.<namespace>.svc.cluster.local

# Step 2: Test external DNS
kubectl exec -it <pod> -- nslookup google.com

# Step 3: Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100

# Step 4: Check CoreDNS ConfigMap
kubectl get configmap coredns -n kube-system -o yaml

# Step 5: Check DNS service endpoint
kubectl get svc kube-dns -n kube-system
kubectl get endpoints kube-dns -n kube-system

# Step 6: Test DNS with specific options
kubectl exec <pod> -- nslookup -debug <service-name>
kubectl exec <pod> -- cat /etc/resolv.conf
```

#### Common DNS Issues

**Issue: DNS 5-second timeout (Linux conntrack race condition)**
```yaml
# Fix: Use dnsPolicy ClusterFirst with ndots reduction
apiVersion: v1
kind: Pod
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"       # Reduce from default 5
      - name: single-request-reopen
        value: ""        # Avoid conntrack race
      - name: timeout
        value: "2"
      - name: attempts
        value: "3"
```

**Issue: CoreDNS overloaded**
```bash
# Check CoreDNS metrics
kubectl top pods -n kube-system -l k8s-app=kube-dns

# Scale CoreDNS
kubectl scale deployment coredns -n kube-system --replicas=5

# Or use NodeLocal DNSCache
# Deploy node-local-dns DaemonSet to cache DNS at each node
```

**Issue: Custom DNS not resolving**
```yaml
# CoreDNS ConfigMap — add custom forward zone
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns-custom
  namespace: kube-system
data:
  custom.server: |
    corp.internal:53 {
        forward . 10.0.0.53 10.0.0.54
        cache 30
    }
```

**Issue: Pod resolv.conf incorrect**
```bash
# Verify pod DNS configuration
kubectl exec <pod> -- cat /etc/resolv.conf
# Expected:
# nameserver 10.96.0.10 (or cluster DNS IP)
# search <namespace>.svc.cluster.local svc.cluster.local cluster.local
# options ndots:5

# If wrong, check dnsPolicy on the pod spec
# ClusterFirst (default), Default (node's DNS), None (custom)
```

### CNI Plugin Failures and IP Exhaustion

#### CNI Binary and Plugin Debugging

```bash
# Check CNI binary presence on node
ls /opt/cni/bin/

# Check CNI configuration
ls /etc/cni/net.d/
cat /etc/cni/net.d/10-*.conflist

# Check CNI DaemonSet pods
kubectl get ds -n kube-system | grep -E "calico|cilium|azure-cni|aws-node"
kubectl logs -n kube-system <cni-pod> --tail=50

# Common error in pod events:
# "Failed to create pod sandbox: ... CNI plugin not initialized"
# Fix: Ensure CNI DaemonSet is Running on all nodes
```

#### IP Exhaustion

**Azure CNI Traditional:**
```bash
# Check allocated IPs per node
kubectl get nodes -o custom-columns=NAME:.metadata.name,PODS:.status.allocatable.pods

# Azure-specific: Check NIC IP configurations
az network nic show --ids <nic-resource-id> --query "ipConfigurations[].privateIpAddress"

# Symptoms: Pods stuck in ContainerCreating, events show "no IPs available"
# Fix: Reduce maxPods per node, resize subnet, or migrate to overlay mode
```

**AWS VPC CNI:**
```bash
# Check IPAMD logs
kubectl logs -n kube-system -l k8s-app=aws-node --tail=100

# Check available IPs on node
kubectl exec -n kube-system <aws-node-pod> -- /app/grpc-health-probe

# ENI limits per instance type
# t3.medium: 3 ENIs × 6 IPs = 17 pods max
# m5.large: 3 ENIs × 10 IPs = 29 pods max

# Enable prefix delegation for higher density
kubectl set env daemonset aws-node -n kube-system ENABLE_PREFIX_DELEGATION=true
kubectl set env daemonset aws-node -n kube-system WARM_PREFIX_TARGET=1
# Now: t3.medium can support ~110 pods
```

**Cilium IPAM:**
```bash
# Check Cilium IPAM status
kubectl -n kube-system exec ds/cilium -- cilium status | grep IPAM

# List allocated IPs
kubectl -n kube-system exec ds/cilium -- cilium ip list

# Check cluster pool allocation
kubectl get ciliumnodes -o yaml | grep -A5 ipam
```

### Network Policy Blocking Traffic

#### Systematic Policy Debugging

```bash
# Step 1: List all policies affecting a namespace
kubectl get networkpolicies -n production
kubectl get ciliumnetworkpolicies -n production 2>/dev/null
kubectl get networkpolicies.p -n production 2>/dev/null  # Calico

# Step 2: Identify which policies select the target pod
kubectl get networkpolicies -n production -o json | \
  jq '.items[] | select(.spec.podSelector.matchLabels | to_entries[] | 
    select(.key == "app" and .value == "backend"))'

# Step 3: Check if default-deny exists
kubectl get networkpolicies -n production -o name | grep deny

# Step 4: Verify pod labels match policy selectors
kubectl get pod <pod-name> -n production --show-labels

# Step 5: Test connectivity and observe drops
```

**Cilium Policy Verdict Monitoring:**
```bash
# Real-time policy decisions
kubectl -n kube-system exec ds/cilium -- cilium monitor --type policy-verdict

# Filter by specific pod
kubectl -n kube-system exec ds/cilium -- cilium monitor \
  --type policy-verdict \
  --to-identity <identity-id>

# Hubble flow observation
kubectl -n kube-system exec ds/cilium -- hubble observe \
  --namespace production \
  --verdict DROPPED \
  --last 50

# Show policy for specific endpoint
kubectl -n kube-system exec ds/cilium -- cilium endpoint list
kubectl -n kube-system exec ds/cilium -- cilium policy get <endpoint-id>
```

**Calico Policy Debugging:**
```bash
# Check Felix logs for denies
kubectl logs -n kube-system -l k8s-app=calico-node -c calico-node | grep -i deny

# Calico specific diagnostics
kubectl -n kube-system exec <calico-node-pod> -c calico-node -- calico-node -felix-live

# Check iptables rules (Calico iptables mode)
kubectl -n kube-system exec <calico-node-pod> -- iptables-save | grep -c cali
```

**Common Fix — Allow DNS When Using Deny-All:**
```yaml
# This is the #1 missed policy when implementing default-deny
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

### Service Mesh Sidecar Issues

#### Sidecar Not Injecting

```bash
# Check namespace label
kubectl get ns production -o jsonpath='{.metadata.labels}'
# Istio: needs istio-injection: enabled
# Linkerd: needs linkerd.io/inject: enabled

# Check mutating webhook
kubectl get mutatingwebhookconfigurations | grep -E "istio|linkerd"

# Check webhook logs
kubectl logs -n istio-system deploy/istiod | grep "inject" | tail -20

# Verify injection by checking pod containers
kubectl get pods -n production -o jsonpath='{range .items[*]}{.metadata.name}: {range .spec.containers[*]}{.name} {end}{"\n"}{end}'
# Should see istio-proxy or linkerd-proxy container

# Force re-injection (restart deployment)
kubectl rollout restart deployment <name> -n production
```

#### Sidecar Crash or Not Ready

```bash
# Check sidecar logs
kubectl logs <pod-name> -c istio-proxy -n production --tail=50
kubectl logs <pod-name> -c linkerd-proxy -n production --tail=50

# Common issues:
# - Certificate errors (expired CA, clock skew)
# - Memory OOM (increase sidecar resource limits)
# - Port conflicts (app using ports 15000-15999 reserved by Envoy)
# - Init container failure (iptables rules not applied)

# Check init container
kubectl logs <pod-name> -c istio-init -n production

# Verify iptables redirect rules in pod network namespace
kubectl exec <pod-name> -c istio-proxy -- iptables -t nat -L -n
```

#### Traffic Not Flowing Through Mesh

```bash
# Istio: Check proxy sync status
istioctl proxy-status

# Check if Envoy has correct configuration
istioctl proxy-config clusters <pod-name> -n production
istioctl proxy-config routes <pod-name> -n production
istioctl proxy-config listeners <pod-name> -n production

# Envoy access logs
kubectl logs <pod-name> -c istio-proxy -n production | grep "response_code"

# Linkerd: Check proxy status
linkerd viz stat deploy -n production
linkerd viz tap deploy/<name> -n production
```

### Advanced Debugging Tools

#### kubectl debug (Ephemeral Containers)

```bash
# Attach debug container to running pod (K8s 1.25+)
kubectl debug -it <pod-name> -n production \
  --image=nicolaka/netshoot \
  --target=<container-name>
# This shares the pod's network namespace — full access to pod networking

# Debug on node level
kubectl debug node/<node-name> -it --image=ubuntu
# Access host filesystem at /host, host network namespace
```

#### tcpdump in Pods

```bash
# Option 1: Ephemeral debug container
kubectl debug -it <pod-name> -n production --image=nicolaka/netshoot -- \
  tcpdump -i eth0 -nn port 8080

# Option 2: From node (capture pod's veth)
# Find pod's veth on the node
POD_ID=$(kubectl get pod <pod-name> -o jsonpath='{.metadata.uid}')
# On node: find interface in /sys/class/net/*/iflink matching pod's eth0 ifindex

# Option 3: Using nsenter from node debug pod
kubectl debug node/<node-name> -it --image=nicolaka/netshoot
# Inside: find pod PID and nsenter its network namespace
nsenter -t <pid> -n tcpdump -i eth0 -nn -c 100

# Useful tcpdump filters:
tcpdump -i eth0 -nn 'tcp port 8080'                    # Specific port
tcpdump -i eth0 -nn 'host 10.244.1.5'                  # Specific host
tcpdump -i eth0 -nn 'tcp[tcpflags] & tcp-rst != 0'     # TCP resets
tcpdump -i eth0 -nn 'tcp[tcpflags] & tcp-syn != 0'     # New connections
tcpdump -i any -nn 'udp port 53'                       # DNS queries
```

#### Network Debugging Toolkit

```bash
# Deploy a comprehensive debug pod
kubectl run netdebug --rm -it --image=nicolaka/netshoot -- bash

# Inside netshoot container:
# DNS testing
dig +short kubernetes.default.svc.cluster.local
dig +trace example.com

# HTTP testing
curl -v --connect-timeout 5 http://service:8080/health
curl -k https://service:443/health

# TCP connectivity
nc -zv <ip> <port>

# Bandwidth testing
iperf3 -c <target-pod-ip> -t 10

# Route inspection
ip route show
ip neigh show
ss -tlnp

# MTU testing
ping -M do -s 1400 <target-ip>

# Traceroute
traceroute -n <target-ip>
mtr --no-dns <target-ip>
```

#### Cilium Connectivity Test

```bash
# Cilium built-in connectivity test suite
cilium connectivity test

# This tests:
# - Pod-to-Pod (same node, cross-node)
# - Pod-to-Service
# - Pod-to-External
# - Network Policy enforcement
# - DNS resolution
# Results identify exactly which connectivity path is broken
```

### Cloud-Specific Troubleshooting

#### AKS

```bash
# Check Azure CNI pod status
kubectl get pods -n kube-system -l k8s-app=azure-cni

# AKS network troubleshooting
az aks check-acr --resource-group myRG --name myCluster --acr myregistry.azurecr.io

# Check effective NSG rules on node
az network nic list-effective-nsg --ids <nic-id>

# AKS-specific: kubenet vs azure-cni issues
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name} {.spec.podCIDR}{"\n"}{end}'
```

#### EKS

```bash
# Check VPC CNI plugin
kubectl logs -n kube-system -l k8s-app=aws-node --tail=50

# ENI allocation issues
kubectl get nodes -o custom-columns=NAME:.metadata.name,INSTANCE:.spec.providerID
aws ec2 describe-network-interfaces --filters Name=attachment.instance-id,Values=<instance-id>

# Security Group verification
aws ec2 describe-security-groups --group-ids <sg-id> --query "SecurityGroups[].IpPermissions"

# EKS Pod identity / IRSA networking
kubectl exec <pod> -- curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

#### GKE

```bash
# GKE Dataplane V2 diagnostics
gcloud container clusters describe CLUSTER --format='get(networkConfig.datapathProvider)'

# Check network policy logging
gcloud logging read 'resource.type="k8s_container" AND jsonPayload.connection.direction="ingress"' --limit 50

# GKE connectivity test
gcloud network-management connectivity-tests create test-1 \
  --source-instance=projects/PROJECT/zones/ZONE/instances/INSTANCE \
  --destination-ip=<pod-ip> \
  --destination-port=8080 \
  --protocol=TCP
```

### Quick Reference: Diagnostic Commands

```bash
# === Cluster Health ===
kubectl get nodes -o wide
kubectl get cs                          # Component status (deprecated but useful)
kubectl cluster-info

# === Pod Networking ===
kubectl get pods -o wide -A             # All pods with IPs and nodes
kubectl describe pod <name>             # Events, conditions
kubectl get events --sort-by=.lastTimestamp

# === Services ===
kubectl get svc -A                      # All services
kubectl get endpoints <svc-name>        # Backend pod IPs for service
kubectl describe svc <name>             # Service details + endpoints

# === DNS ===
kubectl get svc kube-dns -n kube-system
kubectl get endpoints kube-dns -n kube-system
kubectl logs -n kube-system -l k8s-app=kube-dns -c coredns

# === CNI ===
kubectl get ds -n kube-system           # DaemonSet health
kubectl get pods -n kube-system -o wide # CNI pods per node

# === Network Policies ===
kubectl get networkpolicies -A
kubectl get ciliumnetworkpolicies -A 2>/dev/null
kubectl get globalnetworkpolicies 2>/dev/null

# === Service Mesh ===
istioctl analyze -n production 2>/dev/null
linkerd check 2>/dev/null
```

---

**Analysis only — verify against vendor documentation before applying.**
