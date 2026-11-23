# Deploy app
git clone <repo>
docker-compose up -d
export KUBECONFIG=./kubeconfig/kubeconfig.yaml
kubectl get nodes
kubectl apply -f deployment/

# Рішення — збілдити image на хості і імпортувати його в k3s:
## 1. Збілдити image локальним Docker
docker build -t myapp:latest ./app
## 2. Імпортувати в k3s контейнер
docker save myapp:latest | docker exec -i kube-helm k3s ctr images import -
