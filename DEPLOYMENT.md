# Deployment Guide – Automation Hub

Docker, Kubernetes (Kustomize), and Helm deployment for Automation Hub (Data & Connectors, Creative Studio, Messaging, Admin, Tickets).

## Table of Contents

- [Docker](#docker)
- [Kubernetes (Kustomize)](#kubernetes-kustomize)
- [Helm](#helm)
- [CI/CD](#cicd)
- [Production checklist](#production-checklist)

---

## Docker

### Build

```bash
docker build -f docker/Dockerfile -t automation-hub:latest .
```

### Run

```bash
docker run -d \
  -p 8000:8000 \
  -e SESSION_SECRET=your-secret \
  -e APP_DATA_DIR=/app/data \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  -v hub-data:/app/data \
  --name automation-hub \
  automation-hub:latest
```

### Docker Compose

```bash
# Optional: create .env with SESSION_SECRET, SMTP_USER, SMTP_PASSWORD, ADMIN_EMAIL
cd docker
docker-compose -f docker-compose.yml up -d

# Logs
docker-compose -f docker-compose.yml logs -f automation-hub

# Stop
docker-compose -f docker-compose.yml down
```

Or use Makefile from project root:
```bash
make docker-compose-up
make docker-compose-logs
make docker-compose-down
```

Data (DB + data_pools) is stored in the `hub-data` volume. Uploads/outputs can be bind-mounted from the host.

### Docker Compose with Nginx (recommended for large downloads)

If Excel/ZIP downloads hit **upstream timed out**, put Nginx in front with long timeouts and streaming:

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

Or use Makefile:
```bash
make docker-compose-up-nginx
```

Then open **http://localhost** (port 80). Nginx proxies to the app with 10‑minute timeouts and no buffering so large downloads don’t get stuck. See `nginx/README.md`.

### Docker Compose with Redis (optional)

Use Redis for caching, rate limiting, or future server-side session store:

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.redis.yml up -d
```

Or use Makefile:
```bash
make docker-compose-up-redis
```

This starts Redis on port 6379 and sets `REDIS_URL=redis://redis:6379/0` for the app. The app uses it when available (see `redis_util.py`). You can combine with Nginx:

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml -f docker-compose.redis.yml up -d
```

---

## Kubernetes (Kustomize)

### 1. Set image in `k8s/kustomization.yaml`

```yaml
images:
  - name: automation-hub
    newName: your-registry/automation-hub
    newTag: latest
```

### 2. Create namespace and secrets

```bash
kubectl create namespace automation-hub

kubectl create secret generic automation-hub-secrets \
  --from-literal=SESSION_SECRET="$(openssl rand -hex 32)" \
  --from-literal=SMTP_USER=your@email.com \
  --from-literal=SMTP_PASSWORD=your-password \
  -n automation-hub
```

### 3. Deploy

```bash
kubectl apply -k k8s/ -n automation-hub
kubectl rollout status deployment/automation-hub -n automation-hub
```

### 4. Verify

```bash
kubectl get all,pvc -n automation-hub
kubectl logs -f deployment/automation-hub -n automation-hub
```

### 5. Access

```bash
kubectl port-forward svc/automation-hub-service 8000:80 -n automation-hub
# Open http://localhost:8000
```

See `k8s/README.md` for details and PVC/Ingress options.

---

## Helm

### Install / upgrade

```bash
# From repo root
helm upgrade --install automation-hub ./helm/automation-hub \
  -n automation-hub \
  --create-namespace \
  --set image.repository=your-registry/automation-hub \
  --set image.tag=latest \
  --set secret.sessionSecret=your-32-char-secret
```

### Override with values file

```yaml
# my-values.yaml
image:
  repository: myregistry/automation-hub
  tag: v1.0.0

secret:
  create: true
  sessionSecret: "your-secret"
  smtpUser: "notifications@example.com"
  smtpPassword: "xxx"
  adminEmail: "admin@example.com"

ingress:
  enabled: true
  hosts:
    - host: hub.example.com
      paths:
        - path: /
          pathType: Prefix
```

```bash
helm upgrade --install automation-hub ./helm/automation-hub -n automation-hub -f my-values.yaml
```

### Uninstall

```bash
helm uninstall automation-hub -n automation-hub
```

See `helm/automation-hub/README.md` for all parameters.

---

## CI/CD

### GitHub Actions

- **ci-cd.yml**: On push to `main`/`develop`, runs tests, builds image, and (on develop) deploys to development; on release, deploys to production. Uses Kustomize and `deployment/automation-hub`.
- **k8s-deploy.yml**: Manual workflow to deploy a given image tag to development/staging/production. Set `KUBECONFIG` secret per environment.

### Required secrets

- `GITHUB_TOKEN` (provided by GitHub)
- `KUBECONFIG_DEV` / `KUBECONFIG_PROD` (or `KUBECONFIG` for k8s-deploy) – kubeconfig for the target cluster

### Manual deploy (workflow_dispatch)

```bash
gh workflow run k8s-deploy.yml -f environment=production -f image_tag=v1.0.0
```

---

## Production checklist

- [ ] Set strong `SESSION_SECRET` (e.g. `openssl rand -hex 32`)
- [ ] Configure SMTP (SMTP_USER, SMTP_PASSWORD, ADMIN_EMAIL) for notifications and password reset
- [ ] Use TLS for Ingress (e.g. cert-manager + Let’s Encrypt)
- [ ] Use ReadWriteMany storage for multi-replica PVCs, or run a single replica with ReadWriteOnce
- [ ] Adjust resource requests/limits and HPA in deployment / Helm values
- [ ] Do not commit real secrets; use Kubernetes Secrets or Helm values files excluded from git
