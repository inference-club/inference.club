#!/usr/bin/env bash
# Single-node k3s for the inference.club VPS. Idempotent: safe to re-run on
# every deploy. Shipped and executed by infra/deployment.ts ("k3s").
#
# This script owns only the node-level layer:
#   1. k3s itself (first install only, at K3S_VERSION; later upgrades are
#      automatic, see k8s/platform/system-upgrade)
#   2. the config for the Traefik that k3s bundles (a HelmChartConfig file)
#   3. the one-time Argo CD bootstrap
# Everything else (cert-manager, Sealed Secrets, the app) is installed by
# Argo CD from the k8s/ directory of this repo.
set -euo pipefail

# Version for a first install only.
K3S_VERSION="${K3S_VERSION:-v1.37.2+k3s1}"
ARGOCD_VERSION="${ARGOCD_VERSION:-v3.6.2}"
REPO_URL="${REPO_URL:-https://github.com/inference-club/inference.club.git}"
# Public ports Traefik is exposed on. Overridden to 8080/8443 while k3s ran
# next to the old docker compose stack; 80/443 is the normal state.
TRAEFIK_WEB_PORT="${TRAEFIK_WEB_PORT:-80}"
TRAEFIK_WEBSECURE_PORT="${TRAEFIK_WEBSECURE_PORT:-443}"

# ---- 1. k3s ----------------------------------------------------------------
install -d -m 0755 /etc/rancher/k3s /var/lib/rancher/k3s/server/manifests

cat > /etc/rancher/k3s/config.yaml <<'EOF'
# Managed by inference.club infra/templates/k3s.sh -- do not edit by hand.
write-kubeconfig-mode: "0600"
node-name: inference-club
# Small disk: collect unused images early.
kubelet-arg:
  - image-gc-high-threshold=70
  - image-gc-low-threshold=60
EOF

# ---- 2. Traefik config -----------------------------------------------------
# Must exist before k3s first starts, so Traefik never grabs ports it should
# not. k3s watches this directory and re-applies the file when it changes.
cat > /var/lib/rancher/k3s/server/manifests/traefik-config.yaml <<EOF
# Managed by inference.club infra/templates/k3s.sh -- do not edit by hand.
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    ports:
      web:
        exposedPort: ${TRAEFIK_WEB_PORT}
        http:
          redirections:
            entryPoint:
              to: websecure
              scheme: https
              permanent: true
      websecure:
        exposedPort: ${TRAEFIK_WEBSECURE_PORT}
        transport:
          respondingTimeouts:
            # Default is 60s, which cuts off large media uploads.
            readTimeout: 600s
    service:
      spec:
        # Keep the real client IP (rate limiting and logs depend on it).
        externalTrafficPolicy: Local
    accessLog:
      enabled: true
EOF

# Install only if k3s is missing. After that, upgrades are done in-cluster by
# system-upgrade-controller (k8s/platform/system-upgrade), so this script must
# never reinstall K3S_VERSION over a newer running version.
if ! command -v k3s >/dev/null 2>&1; then
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" sh -
else
    systemctl is-active --quiet k3s || systemctl start k3s
fi

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
for _ in $(seq 1 60); do
    kubectl get node inference-club >/dev/null 2>&1 && break
    sleep 2
done
kubectl wait --for=condition=Ready node/inference-club --timeout=180s

# ---- 3. Argo CD bootstrap (first run only) ---------------------------------
# After this, Argo CD manages itself from k8s/platform/argocd in the repo.
if ! kubectl get namespace argocd >/dev/null 2>&1; then
    kubectl create namespace argocd
    kubectl apply -n argocd --server-side \
        -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
    kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
    kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s
fi
if ! kubectl -n argocd get application root >/dev/null 2>&1; then
    kubectl apply -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  project: default
  source:
    repoURL: ${REPO_URL}
    targetRevision: main
    path: k8s/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF
fi

echo "k3s: ok ($(k3s --version | awk 'NR==1{print $3}'))"
