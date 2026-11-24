# kub-helm — Zero-Downtime Deployment Demo

Kubernetes кластер (k3s) з Traefik Ingress, Prometheus, Grafana та демонстрацією zero-downtime rolling update під навантаженням.

## Стек

| Компонент | Роль |
|---|---|
| k3s | Kubernetes кластер у Docker |
| Traefik | Ingress controller (вбудований у k3s) |
| FastAPI | Python застосунок |
| Prometheus | Збір метрик |
| Grafana | Візуалізація метрик |
| k6 | Навантажувальне тестування |

## Запуск

### 1. Старт кластера
```bash
docker-compose up -d
export KUBECONFIG=./kubeconfig/kubeconfig.yaml
```

### 2. Збірка та імпорт image
```bash
docker build -t myapp:latest ./app
docker save myapp:latest | docker exec -i kube-helm ctr -n k8s.io images import -
```

### 3. Деплой
```bash
kubectl apply -f deployment/
```

### 4. Перевірка
```bash
kubectl get pods
curl http://localhost/
curl http://localhost/health
```

### 5. Grafana
Відкрити: http://localhost:3000
Login: `admin` / `admin`

### 6. Prometheus
Відкрити: http://localhost:9090

## Zero-Downtime Deployment

### Стратегія
```yaml
replicas: 3
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0   # жоден старий под не видаляється поки новий не Ready
    maxSurge: 1         # +1 зайвий под під час оновлення
```

### Деплой нової версії
```bash
./deploy.sh <version>
# Приклад: ./deploy.sh 5
```

### Тест під навантаженням
```bash
# Термінал 1 — запуск навантаження (100 RPS, 2 хвилини)
docker-compose --profile test run k6

# Термінал 2 — деплой нової версії під час навантаження
./deploy.sh 5
```

### Результат експерименту

| Метрика | Значення |
|---|---|
| Тривалість тесту | 2 хвилини |
| RPS | 100 |
| Всього запитів | ~12 000 |
| Помилки | 0% |
| p95 latency | < 500ms |

> Скріншоти Grafana — після проведення тесту

## GitHub Actions

При кожному push в `main` (зміни в `app/`) автоматично:
1. Білдиться новий Docker image
2. Пушиться на `ghcr.io/maksim-web-dev/kub-helm:<номер_збірки>`