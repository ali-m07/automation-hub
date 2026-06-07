# Kubernetes – Automation Hub

Deploy Automation Hub (Data & Connectors, Creative Studio, Messaging, Admin, Tickets) to Kubernetes.

## Prerequisites

- `kubectl` configured for your cluster
- (Optional) Helm 3 for chart deployment

## Quick start (Kustomize)

1. **Create namespace**
   ```bash
   kubectl create namespace automation-hub
   ```

2. **Create secrets** (do not commit real values)
   ```bash
   kubectl create secret generic automation-hub-secrets \
     --from-literal=SESSION_SECRET="$(openssl rand -hex 32)" \
     --from-literal=SMTP_USER=your@email.com \
     --from-literal=SMTP_PASSWORD=your-password \
     -n automation-hub
   ```

3. **Set image** in `kustomization.yaml`:
   ```yaml
   images:
     - name: automation-hub
       newName: your-registry/automation-hub
       newTag: latest
   ```

4. **Deploy**
   ```bash
   kubectl apply -k k8s/ -n automation-hub
   ```

5. **Check**
   ```bash
   kubectl get all,pvc -n automation-hub
   ```

## Files

| File | Purpose |
|------|--------|
| `configmap.yaml` | Non-sensitive env (APP_DATA_DIR, SMTP host/port) |
| `deployment.yaml` | Deployment, probes, volume mounts |
| `service.yaml` | Service + Ingress |
| `pvc.yaml` | PVCs for uploads, outputs, app data (DB + data_pools) |
| `hpa.yaml` | Horizontal Pod Autoscaler |
| `kustomization.yaml` | Kustomize base |
| `secrets.yaml.example` | Example secret (copy and fill) |

## Data persistence

- **uploads**: 20Gi PVC
- **outputs**: 50Gi PVC  
- **data**: 10Gi PVC for `app.db` and `data_pools/` (APP_DATA_DIR=/app/data)

## Helm (optional)

From repo root:

```bash
helm upgrade --install automation-hub ./helm/automation-hub -n automation-hub --create-namespace
```

See `helm/automation-hub/README.md` for values and overrides.
