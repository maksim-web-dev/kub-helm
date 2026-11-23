#!/bin/bash
set -e

VERSION=$1
IMAGE="ghcr.io/maksim-web-dev/kub-helm:${VERSION}"
KUBECONFIG_PATH="./kubeconfig/kubeconfig.yaml"

if [ -z "$VERSION" ]; then
  echo "Usage: ./deploy.sh <version>"
  echo "Example: ./deploy.sh 5"
  exit 1
fi

echo "Pulling image ${IMAGE}..."
docker pull "${IMAGE}"

echo "Importing into k3s..."
docker save "${IMAGE}" | docker exec -i kube-helm ctr -n k8s.io images import -

echo "Updating deployment..."
kubectl --kubeconfig="${KUBECONFIG_PATH}" set image deployment/myapp myapp="${IMAGE}"

echo "Watching rollout..."
kubectl --kubeconfig="${KUBECONFIG_PATH}" rollout status deployment/myapp