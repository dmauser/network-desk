# Skill: Service Mesh Design

## Purpose

Guide architecture decisions for service mesh implementations in Kubernetes environments. Covers Istio and Linkerd in depth, including when to adopt (or avoid) a service mesh, mTLS configuration, traffic management, observability, and the emerging ambient mesh paradigm.

## Core Knowledge

### When to Use a Service Mesh

**Adopt a service mesh when:**
- You need mutual TLS (mTLS) between all services without application changes
- Complex traffic routing is required: canary deployments, A/B testing, traffic mirroring
- Distributed tracing and L7 metrics are needed across many services
- Retry, timeout, and circuit-breaking policies should be managed outside application code
- Compliance requires encryption in transit for all east-west traffic
- Multi-cluster service communication with unified policy

**Avoid a service mesh when:**
- Fewer than 10-15 microservices (operational overhead exceeds value)
- Team lacks Kubernetes operational maturity
- Latency sensitivity is extreme (sub-millisecond per hop matters)
- Simple Kubernetes Services and NetworkPolicy meet requirements
- Budget doesn't allow for the ~15-25% memory overhead of sidecars per pod

### Istio Architecture

Istio is the most widely deployed service mesh, providing a complete platform for service-to-service communication.

**Components:**
- **istiod** — Control plane: Pilot (config/discovery), Citadel (certificate management), Galley (config validation)
- **Envoy sidecar** — Data plane proxy injected into every pod
- **Ingress Gateway** — Edge proxy for north-south traffic
- **Egress Gateway** — Controlled exit point for external traffic

**Core Resources:**

#### VirtualService — Traffic routing rules

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: reviews-route
  namespace: production
spec:
  hosts:
    - reviews
  http:
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: reviews
            subset: v2
          weight: 100
    - route:
        - destination:
            host: reviews
            subset: v1
          weight: 90
        - destination:
            host: reviews
            subset: v2
          weight: 10
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: connect-failure,refused-stream,503
      timeout: 10s
```

#### DestinationRule — Service versions, load balancing, connection pool

```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: reviews-destination
  namespace: production
spec:
  host: reviews
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: UPGRADE
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    outlierDetection:
      consecutive5xxErrors: 3
      interval: 30s
      baseEjectionTime: 60s
      maxEjectionPercent: 50
    loadBalancer:
      simple: LEAST_REQUEST
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
      trafficPolicy:
        connectionPool:
          http:
            http2MaxRequests: 500
```

#### PeerAuthentication — mTLS configuration

```yaml
# Mesh-wide strict mTLS
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT
---
# Namespace-level permissive (for migration)
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: permissive-mtls
  namespace: legacy-apps
spec:
  mtls:
    mode: PERMISSIVE
---
# Port-level exception
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: health-check-exception
  namespace: production
spec:
  selector:
    matchLabels:
      app: api
  portLevelMtls:
    8081:
      mode: DISABLE  # Health check port — no mTLS
  mtls:
    mode: STRICT
```

#### AuthorizationPolicy — L7 access control

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: api-access
  namespace: production
spec:
  selector:
    matchLabels:
      app: api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/production/sa/frontend"
              - "cluster.local/ns/production/sa/mobile-bff"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/v1/*"]
    - from:
        - source:
            principals:
              - "cluster.local/ns/monitoring/sa/prometheus"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/metrics", "/healthz"]
```

#### Traffic Mirroring (Shadow Traffic)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: reviews-mirror
spec:
  hosts:
    - reviews
  http:
    - route:
        - destination:
            host: reviews
            subset: v1
          weight: 100
      mirror:
        host: reviews
        subset: v2
      mirrorPercentage:
        value: 50.0
```

#### Fault Injection (Chaos Testing)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: ratings-fault
spec:
  hosts:
    - ratings
  http:
    - fault:
        delay:
          percentage:
            value: 10
          fixedDelay: 5s
        abort:
          percentage:
            value: 5
          httpStatus: 503
      route:
        - destination:
            host: ratings
```

### Linkerd Architecture

Linkerd is a lightweight, security-focused service mesh designed for simplicity and low resource consumption.

**Components:**
- **Control plane** — destination (service discovery), identity (mTLS certificates), proxy-injector (sidecar injection)
- **linkerd-proxy** — Ultralight Rust-based data plane proxy (~10MB memory per sidecar)
- **linkerd-viz** — Optional observability extension (Prometheus, dashboard)

**Key Differentiators from Istio:**
- Significantly lower resource footprint
- Simpler operational model — fewer CRDs, less configuration surface
- Automatic mTLS with zero configuration
- No VirtualService/DestinationRule complexity
- Faster proxy startup time

#### ServiceProfile — Per-route metrics and retries

```yaml
apiVersion: linkerd.io/v1alpha2
kind: ServiceProfile
metadata:
  name: api.production.svc.cluster.local
  namespace: production
spec:
  routes:
    - name: GET /api/v1/users
      condition:
        method: GET
        pathRegex: /api/v1/users
      isRetryable: true
      timeout: 5s
    - name: POST /api/v1/users
      condition:
        method: POST
        pathRegex: /api/v1/users
      isRetryable: false
      timeout: 10s
    - name: GET /healthz
      condition:
        method: GET
        pathRegex: /healthz
      isRetryable: true
      timeout: 2s
```

#### TrafficSplit — Canary deployments (SMI spec)

```yaml
apiVersion: split.smi-spec.io/v1alpha4
kind: TrafficSplit
metadata:
  name: api-canary
  namespace: production
spec:
  service: api
  backends:
    - service: api-stable
      weight: 900
    - service: api-canary
      weight: 100
```

#### Server / ServerAuthorization — Fine-grained access control

```yaml
apiVersion: policy.linkerd.io/v1beta2
kind: Server
metadata:
  name: api-server
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api
  port: 8080
  proxyProtocol: HTTP/2
---
apiVersion: policy.linkerd.io/v1beta2
kind: ServerAuthorization
metadata:
  name: allow-frontend
  namespace: production
spec:
  server:
    name: api-server
  client:
    meshTLS:
      serviceAccounts:
        - name: frontend
          namespace: production
```

#### HTTPRoute (Linkerd + Gateway API)

```yaml
apiVersion: policy.linkerd.io/v1beta3
kind: HTTPRoute
metadata:
  name: api-route
  namespace: production
spec:
  parentRefs:
    - name: api-server
      kind: Server
      group: policy.linkerd.io
  rules:
    - matches:
        - path:
            value: /api/v1/admin
      filters:
        - type: RequestHeaderModifier
          requestHeaderModifier:
            set:
              - name: x-require-auth
                value: "true"
```

### Ambient Mesh vs Sidecar

#### Traditional Sidecar Model
- Envoy/linkerd-proxy injected as container in every pod
- **Pros:** Per-pod L7 policy, per-pod metrics, full feature set
- **Cons:** Memory overhead (50-100MB per pod), CPU overhead, upgrade complexity (must restart pods), startup latency, application compatibility issues

#### Ambient Mesh (Istio)
Istio's ambient mesh mode eliminates sidecars by splitting the data plane:

**ztunnel (Zero-Trust Tunnel):** Node-level DaemonSet providing:
- L4 traffic management
- mTLS encryption
- L4 authorization policies
- Minimal overhead — shared per node

**waypoint proxy:** Optional per-namespace/service L7 proxy:
- Deployed only where L7 features are needed
- Handles HTTP routing, L7 auth policies, retries
- Scales independently of application pods

```yaml
# Enable ambient mode for a namespace
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    istio.io/dataplane-mode: ambient
---
# Deploy waypoint proxy for L7 features
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: production-waypoint
  namespace: production
  labels:
    istio.io/waypoint-for: service
spec:
  gatewayClassName: istio-waypoint
  listeners:
    - name: mesh
      port: 15008
      protocol: HBONE
```

**When to choose ambient over sidecar:**
- Large number of pods where sidecar overhead is significant
- Teams find sidecar injection/management complex
- Only L4 mTLS is needed (ztunnel is sufficient)
- Gradual adoption — add L7 waypoints only where needed
- Serverless/batch workloads where sidecar startup time is problematic

### mTLS Implementation Patterns

#### Zero-Config mTLS (Linkerd)
```bash
# Inject the mesh — mTLS is automatic
kubectl get deploy -n production -o yaml | linkerd inject - | kubectl apply -f -
# Verify mTLS
linkerd viz edges -n production
```

#### Gradual mTLS Rollout (Istio)
```yaml
# Phase 1: Permissive (accepts both plain and mTLS)
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: PERMISSIVE
---
# Phase 2: Strict (only mTLS accepted)
# Apply after verifying all clients are in mesh
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT
```

### Observability

#### Istio Metrics
```yaml
# Custom telemetry — add request classification
apiVersion: telemetry.istio.io/v1alpha1
kind: Telemetry
metadata:
  name: api-telemetry
  namespace: production
spec:
  selector:
    matchLabels:
      app: api
  metrics:
    - providers:
        - name: prometheus
      overrides:
        - tagOverrides:
            request_classification:
              operation: UPSERT
              value: "request.headers['x-request-type'] | 'unknown'"
```

#### Linkerd Observability
```bash
# Real-time traffic monitoring
linkerd viz stat deploy -n production
linkerd viz top deploy/api -n production
linkerd viz routes deploy/api -n production

# Per-route success rates
linkerd viz routes deploy/api --to svc/database -n production
```

## Cloud-Specific Guidance

### AKS
- **Istio:** Available as AKS managed add-on (Istio-based service mesh)
  ```bash
  az aks mesh enable --resource-group myRG --name myCluster
  az aks mesh enable-ingress-gateway --resource-group myRG --name myCluster \
    --ingress-gateway-type external
  ```
- **Open Service Mesh (OSM):** Deprecated — migrate to Istio
- **Linkerd:** Install via Helm (not managed by AKS)

### EKS
- **App Mesh:** AWS-native (Envoy-based) — limited adoption, consider Istio/Linkerd
- **Istio:** Install via istioctl or Helm; integrates with AWS ALB via Gateway
- **Linkerd:** Install via Helm; lightweight option for EKS

### GKE
- **Anthos Service Mesh (ASM):** Google-managed Istio distribution
  ```bash
  gcloud container fleet mesh enable --project PROJECT_ID
  gcloud container fleet mesh update \
    --management automatic \
    --memberships CLUSTER_NAME
  ```
- **Traffic Director:** Cloud-native xDS-compatible control plane
- **Linkerd:** Install via Helm (not GKE-managed)

## Decision Matrix: Istio vs Linkerd

| Criteria | Istio | Linkerd |
|----------|-------|---------|
| **Resource overhead** | Higher (50-100MB/sidecar) | Lower (~10MB/sidecar) |
| **Feature richness** | Very high (VirtualService, fault injection, etc.) | Moderate (focused on core needs) |
| **Operational complexity** | High (many CRDs, config options) | Low (simple install, few knobs) |
| **L7 traffic management** | Advanced (regex routing, mirroring, fault injection) | Basic (retries, timeouts, splits) |
| **mTLS** | Configurable (STRICT/PERMISSIVE/DISABLE) | Always on (zero config) |
| **Multi-cluster** | Native support (mesh federation) | Mirror mode (simpler) |
| **Ambient mesh** | Available (ztunnel + waypoint) | Not applicable |
| **Community/ecosystem** | Largest (CNCF graduated) | Growing (CNCF graduated) |
| **Best for** | Complex routing, multi-cluster, full L7 control | Simplicity, low overhead, security-first |

## Troubleshooting Service Mesh Issues

### Sidecar Not Injecting
```bash
# Check namespace label
kubectl get ns production --show-labels
# Istio: needs istio-injection=enabled
# Linkerd: needs linkerd.io/inject=enabled

# Check webhook
kubectl get mutatingwebhookconfigurations

# Pod annotation to skip injection
metadata:
  annotations:
    sidecar.istio.io/inject: "false"     # Istio
    linkerd.io/inject: disabled           # Linkerd
```

### mTLS Connection Failures
```bash
# Istio: check peer authentication mode
istioctl x describe pod <pod-name> -n production

# Verify certificate chain
istioctl proxy-config secret <pod-name> -n production

# Linkerd: check identity
linkerd viz edges -n production
linkerd identity -n production
```

### High Latency Through Mesh
```bash
# Istio: check Envoy stats
istioctl proxy-config clusters <pod-name> -n production
kubectl exec <pod-name> -c istio-proxy -- curl localhost:15000/stats | grep retry

# Linkerd: check latency percentiles
linkerd viz stat deploy -n production -t 1m
```

---

**Analysis only — verify against vendor documentation before applying.**
