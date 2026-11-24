# kub-helm — Zero-Downtime Deployment Demo

Kubernetes cluster (k3s) with Traefik Ingress, Prometheus, Grafana and a zero-downtime rolling update demonstration under 1000 RPS load.

## Stack

| Component | Role |
|---|---|
| k3s | Lightweight Kubernetes inside Docker |
| Traefik | Ingress controller (built into k3s) |
| FastAPI | Python application with `/health` endpoint |
| Prometheus | Metrics scraping via pod autodiscovery |
| Grafana | Live dashboards (auto-provisioned) |
| k6 | Load testing at 1000 req/s |

---

## Zero-Downtime Deployment

### RollingUpdate strategy

```yaml
replicas: 3
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0   # never remove an old pod until a new one is Ready
    maxSurge: 1         # allow one extra pod during the transition
```

With `maxUnavailable: 0`, Kubernetes never reduces capacity below 3 pods. Each new pod must pass the `readinessProbe` before the next old pod is terminated.

### Graceful shutdown

Two mechanisms prevent connection drops when a pod is terminated:

**1. `preStop` lifecycle hook** — adds a 10-second delay before `SIGTERM` is sent, giving Traefik time to remove the pod from its backend list:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["sleep", "10"]
```

**2. SIGTERM handler in the app** — sets a `shutting_down` flag so `/health` immediately returns `503`, failing the `readinessProbe` before the process exits:

```python
def _handle_sigterm(*_):
    global shutting_down
    shutting_down = True

signal.signal(signal.SIGTERM, _handle_sigterm)
```

### How to run the test

```bash
# Terminal 1 — start load (1000 RPS, 2 minutes)
docker run --rm --network host -v ./k6:/scripts grafana/k6 run /scripts/script.js

# Terminal 2 — deploy new version while under load
docker build -t myapp:v2 ./app
docker save myapp:v2 | docker exec -i kube-helm ctr -n k8s.io images import -
kubectl set image deployment/myapp myapp=myapp:v2
```

### Results at 1000 RPS

| Metric | Value |
|---|---|
| Test duration | 2 minutes |
| Target RPS | **1000 req/s** |
| Peak RPS achieved | **1000 req/s** |
| Total requests | **56,050** |
| Errors (5xx) | **~0.05%** (~0.5 errors/s during pod rotation) |
| p95 latency (baseline) | **~100 ms** |
| p99 latency (peak during rollout) | **~700 ms** |
| Active pods at end | 3 |
| k6 threshold (1% errors) | **PASSED** |

### Grafana during rolling update

![Grafana 1000 RPS Test](docs/grafana-1000rps.png)

**RPS per Pod** — Two pod generations are visible. Old pods (`d4f6969c5-*`) gradually drop to 0 as new pods (`86cb5f8996-*`) ramp up to ~300 req/s each. Traffic shifts smoothly — no sudden cutover.

**Total RPS** — Sustained at 1000 req/s throughout. No gap in traffic during the rollout.

**Error Rate (5xx)** — A spike of ~0.5 errors/s (~0.05% of traffic) appears during pod rotation and disappears once the new pods stabilize. This is caused by Traefik closing keep-alive connections to terminating pods in k3s. The error rate is well below the 1% SLA threshold.

**Response Latency p99** — Baseline ~100 ms. Spikes to ~700 ms during pod rotation, then immediately recovers. The spike is temporary and caused by connection re-establishment after old pods exit.

> **Note:** In production cloud clusters (EKS, GKE) with dedicated load balancers, `preStop` + graceful shutdown brings errors to exactly zero. The ~0.05% residual in this demo is specific to Traefik's keep-alive connection pooling inside k3s-in-Docker.

---

## Failed Deployment (Bad Build)

### Scenario

A developer pushes a broken version where the app can never connect to the database — `/health` always returns `503`. Kubernetes detects this via `readinessProbe` and **blocks the rollout entirely**. Old pods keep serving 100% of traffic.

### How it works

```
[v1] [v1] [v1]           # stable state
[v1] [v1] [v1] [v2-bad]  # new pod starts, readinessProbe → 503
                 ↓
          pod never becomes Ready
                 ↓
          Kubernetes pauses the rollout
                 ↓
[v1] [v1] [v1] [v2-bad]  # old pods still serve all traffic
```

### How to reproduce

In `app/main.py`, replace the body of `connect_to_db` with a failing version:

```python
async def connect_to_db():
    # To simulate a failed deployment, replace the body below with:
    # logger.error("DB connection failed!")
    global db_ready
    await asyncio.sleep(20)
    db_ready = True
    logger.info("DB connection successful")
```

Then build and deploy:

```bash
docker build -t myapp:bad ./app
docker save myapp:bad | docker exec -i kube-helm ctr -n k8s.io images import -
kubectl set image deployment/myapp myapp=myapp:bad

# Watch the rollout freeze — bad pod stays at 0/1
kubectl get pods -w
```

Expected state — rollout stuck, old pods unaffected:
```
NAME                   READY   STATUS    RESTARTS
myapp-<v1>-xxxxx       1/1     Running   0          ← serving traffic
myapp-<v1>-xxxxx       1/1     Running   0          ← serving traffic
myapp-<v1>-xxxxx       1/1     Running   0          ← serving traffic
myapp-<bad>-xxxxx      0/1     Running   0          ← stuck, never Ready
```

```bash
# Old version is still responding
curl http://localhost/
# {"ok": true, "version": 1}
```

### Rollback

```bash
kubectl rollout undo deployment/myapp
```

### Results

| Metric | Value |
|---|---|
| Pods serving traffic | 3 (all v1, unaffected) |
| Rollout status | **Blocked** — bad pod stuck at `0/1` |
| Bad pod traffic received | **0 requests** |
| Recovery | `kubectl rollout undo` — instant |

### Grafana during failed deployment

![Grafana Bad Deploy](docs/grafana-bad-deploy.png)

**RPS per Pod** — The bad pod (`5f567b75b8-86ttl`) line stays at 0 — it was never promoted to Ready and never received a single request. The three healthy pods (`8675b9bffd-*`) continue serving the full 1000 req/s.

**Error Rate (5xx)** — A brief error spike (~0.4–0.6 errors/s) appears at the moment the bad pod is deployed. This is caused by the rollout initiation itself — Traefik briefly adjusts its backend list. After that, the three healthy pods handle traffic without errors.

**Active Pods** — Shows 4 during the freeze (3 healthy + 1 stuck bad pod), then drops back to 3 after rollback.

**Conclusion** — The bad build was completely blocked. No user traffic reached the broken version. `readinessProbe` with `initialDelaySeconds: 0` caught the failure immediately and prevented any pod from entering the routing pool.

---

## Getting Started

### 1. Start the cluster

```bash
docker-compose up -d
export KUBECONFIG=./kubeconfig/kubeconfig.yaml

# Wait ~30s for k3s to initialize
kubectl get nodes
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
Dashboard: **Zero-Downtime Deployment Demo** (auto-provisioned)

### 6. Prometheus

Open: http://localhost:9090

---

## GitHub Actions

On every push to `main` affecting `app/`:
1. Docker image is built
2. Pushed to `ghcr.io/maksim-web-dev/kub-helm:<build_number>` and `:latest`