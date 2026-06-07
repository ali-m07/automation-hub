# Automation Hub Helm Chart

Deploy Automation Hub (Data & Connectors, Creative Studio, Messaging, Admin, Tickets) with Helm.

## Install

```bash
# From repo root
helm upgrade --install automation-hub ./helm/automation-hub \
  -n automation-hub \
  --create-namespace \
  --set image.repository=your-registry/automation-hub \
  --set image.tag=latest
```

## Override values

Create `my-values.yaml`:

```yaml
image:
  repository: myregistry/automation-hub
  tag: v1.0.0

replicaCount: 3

secret:
  create: true
  sessionSecret: "your-32-char-secret"
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
  tls:
    - secretName: hub-tls
      hosts:
        - hub.example.com

config:
  redisUrl: "redis://your-redis:6379/0"   # optional Redis for caching

persistence:
  data:
    enabled: true
    size: 20Gi
  uploads:
    enabled: true
    size: 30Gi
  outputs:
    enabled: true
    size: 100Gi
```

Then:

```bash
helm upgrade --install automation-hub ./helm/automation-hub -n automation-hub -f my-values.yaml
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `2` |
| `image.repository` | Image repository | `your-registry/automation-hub` |
| `image.tag` | Image tag | `latest` |
| `service.type` | Service type | `LoadBalancer` |
| `ingress.enabled` | Enable Ingress | `false` |
| `config.appDataDir` | App data dir (DB + data_pools) | `/app/data` |
| `secret.create` | Create secret from values | `true` |
| `secret.sessionSecret` | SESSION_SECRET | auto-generated if empty |
| `persistence.data.enabled` | PVC for /app/data | `true` |
| `persistence.data.size` | Size for data PVC | `10Gi` |
| `autoscaling.enabled` | Enable HPA | `true` |
| `autoscaling.minReplicas` | Min replicas | `2` |
| `autoscaling.maxReplicas` | Max replicas | `10` |

## Uninstall

```bash
helm uninstall automation-hub -n automation-hub
# PVCs are retained; delete manually if needed:
# kubectl delete pvc -l app.kubernetes.io/instance=automation-hub -n automation-hub
```
