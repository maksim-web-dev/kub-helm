# kub-helm — Zero-Downtime Deployment Demo

Kubernetes cluster (k3s) with Traefik Ingress, Prometheus, Grafana and a zero-downtime rolling update demonstration under load.

## Stack

| Component | Role |
|---|---|
| k3s | Kubernetes cluster inside Docker |
| Traefik | Ingress controller (built into k3s) |
| FastAPI | Python application |
| Prometheus | Metrics collection |
| Grafana | Metrics visualization |
| k6 | Load testing |

## Zero-Downtime Deployment

### Strategy

```yaml
replicas: 3
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0   # no old pod is removed until a new one is Ready
    maxSurge: 1         # allows +1 extra pod during the update
```

### Deploy a new version

```bash
./deploy.sh <version>
# Example: ./deploy.sh 5
```

### Load test

```bash
# Terminal 1 — start load (1000 RPS, 2 minutes)
docker-compose --profile test run k6

# Terminal 2 — deploy new version while under load
./deploy.sh 5
```

---

### Test 1: Low load (baseline)

| Metric | Value |
|---|---|
| Test duration | 2 minutes |
| Target RPS | 1000 |
| Actual RPS per pod | ~1.5 |
| Total requests | 200+ |
| Errors (5xx) | **0%** |
| p95 latency | **95 ms** |
| p99 latency | **99 ms** |

> This was before switching k6 to `network_mode: host` — traffic was going through Docker bridge, not reaching the cluster at full rate.

### Grafana — Test 1

![Grafana Zero-Downtime Demo](docs/grafana-screenshot.png)

**What it shows:** Three pod generations visible in RPS per Pod panel. Traffic shifts from v1 → v2 smoothly. Zero errors, latency flat throughout.

---

### Test 2: High load — 1000 RPS

k6 configured with `constant-arrival-rate`, `rate: 1000`, `network_mode: host`.
Rolling update triggered at ~t=8s after the test started.

| Metric | Value |
|---|---|
| Test duration | 2 minutes |
| Target RPS | **1000 req/s** |
| Peak RPS achieved | **1000 req/s** |
| Total requests | **71,159** |
| Errors (5xx) | **< 0.06%** (~0.5 errors/s during pod rotation) |
| p95 latency (baseline) | **~100 ms** |
| p95 latency (during rollout) | **~600 ms** |
| p99 latency (peak during rollout) | **~900 ms** |
| Active pods at end | 3 |

### Grafana — Test 2 (1000 RPS)

![Grafana 1000 RPS Test](docs/grafana-1000rps.png)

#### What the screenshot shows

**RPS per Pod** — At 1000 RPS with 3 pods, each pod handles ~300–350 req/s. During the rolling update, up to 9 pod lines appear simultaneously (old + new pods coexisting). Old pods gradually drop to 0 as new pods ramp up.

**Total RPS** — Sustained at 1000 req/s throughout the test, confirming the cluster handled the target load.

**Error Rate (5xx)** — Spikes of ~0.4–0.6 errors/s appeared during pod rotation (~0.05% of total traffic). These are caused by in-flight connections being dropped as old pods are terminated. Well below the 1% SLA threshold.

**Response Latency p95/p99** — Baseline ~100 ms. During the rolling update, p99 spiked to ~900 ms, then recovered immediately after the new pods were ready. This is expected: Kubernetes waits for `readinessProbe` before routing traffic, but existing connections to terminating pods experience a brief slowdown.

#### Conclusion

At 1000 RPS, the rolling update completed with **< 0.06% error rate** — well under the 1% k6 threshold. The deployment passed all thresholds. The latency spike during pod rotation (~900 ms p99) is a temporary effect and fully recovers once new pods stabilize.

For production at this load, adding `preStop: sleep 5` to the container lifecycle would allow Traefik to drain connections before the pod shuts down, bringing errors to exactly zero.

## Failed Deployment (Bad Build)

### Scenario

A developer pushes a broken version where the `/health` endpoint always returns `503`.
Kubernetes detects the failure via `readinessProbe` and **blocks the rollout** — old pods keep serving traffic.

### How it works

```
[v2] [v2] [v2]          # stable state before deploy
[v2] [v2] [v2] [v3-bad] # new pod starts, readinessProbe hits /health → 503
                ↓
         pod never becomes Ready
                ↓
         Kubernetes pauses the rollout
                ↓
[v2] [v2] [v2] [v3-bad] # old pods still serve 100% of traffic
```

### Steps to reproduce

```bash
# Terminal 1 — start load
docker-compose --profile test run k6

# Terminal 2 — deploy bad version
docker build -t myapp:v3-bad ./app   # built from broken code
docker save myapp:v3-bad | docker exec -i kube-helm ctr -n k8s.io images import -
kubectl set image deployment/myapp myapp=myapp:v3-bad

# Watch the rollout freeze
kubectl get pods -w
```

Expected output — rollout is stuck, 1 bad pod never reaches Ready:
```
NAME                     READY   STATUS    RESTARTS   AGE
myapp-<v2>-xxxxx         1/1     Running   0          5m
myapp-<v2>-xxxxx         1/1     Running   0          5m
myapp-<v2>-xxxxx         1/1     Running   0          5m
myapp-<v3-bad>-xxxxx     0/1     Running   0          30s   ← stuck, never Ready
```

```bash
# Service is still responding with v2
curl http://localhost/
# {"ok": true, "version": 2}
```

### Rollback

```bash
kubectl rollout undo deployment/myapp
# deployment.apps/myapp rolled back
```

### Results

| Metric | Value |
|---|---|
| Pods serving traffic | 3 (all v2, unaffected) |
| Rollout status | Blocked — bad pod stuck at `0/1` |
| Recovery | `kubectl rollout undo` — instant |
| Error rate | ~0.1–0.19 req/s (see note below) |
| Latency spike (p99) | ~1 s during rollback |

### Grafana dashboard during failed deployment

![Grafana Bad Deploy](docs/grafana-bad-deploy.png)

#### What the screenshot shows

**RPS per Pod** — `658f458f8f-j4lrn` is the v3-bad pod. Its line eventually drops to 0 and disappears — it was stuck at `0/1 Ready` and was never promoted. The other pods (`658f458f8f-*` and `7c7fd9c646-*`) continued serving traffic throughout.

**Error Rate (5xx)** — A non-zero error rate (~0.1–0.19 errors/s) appeared during pod restarts. This is caused by `initialDelaySeconds: 5` in the readiness probe: for the first 5 seconds after a pod starts, Traefik may still route traffic to it before Kubernetes marks it as not ready. This is a known gap — the fix is a **startupProbe** or reducing `initialDelaySeconds` to 0.

**Response Latency p99** — A spike to ~1 s at the moment of rollback as pods were being recycled.

**Active Pods** — Drops briefly during pod rotation (the dip in the chart), then returns to 3.

#### Conclusion

The bad build was blocked — v3-bad never replaced a single healthy pod. However, the test revealed
a real production concern: `initialDelaySeconds: 5` creates a brief window where Traefik can send
requests to a pod that is not yet ready. For true zero-downtime, pair `readinessProbe` with a
`startupProbe` or set `initialDelaySeconds: 0` with a fast-failing health check.

## Getting Started

### 1. Start the cluster

```bash
docker-compose up -d
export KUBECONFIG=./kubeconfig/kubeconfig.yaml
```

### 2. Build and import the image

```bash
docker build -t myapp:latest ./app
docker save myapp:latest | docker exec -i kube-helm ctr -n k8s.io images import -
```

### 3. Deploy

```bash
kubectl apply -f deployment/
```

### 4. Verify

```bash
kubectl get pods
curl http://localhost/
curl http://localhost/health
```

### 5. Grafana

Open: http://localhost:3000
Login: `admin` / `admin`

### 6. Prometheus

Open: http://localhost:9090

## GitHub Actions

On every push to `main` (changes in `app/`):
1. A new Docker image is built
2. Pushed to `ghcr.io/maksim-web-dev/kub-helm:<build_number>`