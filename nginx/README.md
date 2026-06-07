# Nginx reverse proxy for Automation Hub

Use Nginx in front of the app to avoid **upstream timed out** when downloading large files (ZIP, Excel).

## Why

Without Nginx (or with default Nginx timeouts), large downloads can hit `upstream timed out` because:

- Default `proxy_read_timeout` is 60s; building/sending a large ZIP takes longer.
- Buffering the whole response in Nginx can delay the first byte and cause timeouts.

This config sets:

- **proxy_read_timeout / proxy_send_timeout / proxy_connect_timeout**: 600s (10 min).
- **proxy_buffering off**: stream the response to the client instead of buffering.
- **client_max_body_size 500M**: allow large PSD/Excel uploads.

## Standalone (same host as app)

1. Copy `nginx.conf` to your Nginx config (e.g. `/etc/nginx/nginx.conf` or a file in `/etc/nginx/conf.d/`).
2. Change `upstream automation_hub { server 127.0.0.1:8000; }` if the app runs on another host/port.
3. Reload Nginx: `nginx -t && systemctl reload nginx` (or `nginx -s reload`).

## Docker Compose

From the project root:

```bash
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

This starts Nginx on port 80 and proxies to the app. Large downloads (ZIP/Excel) won’t hit upstream timeout. See `DEPLOYMENT.md`.

## Kubernetes / Helm

If you use **nginx-ingress**, set Ingress annotations so the controller uses long timeouts and no buffering for downloads. See `helm/automation-hub/values.yaml`: `ingress.annotations` already includes:

- `proxy-read-timeout`, `proxy-send-timeout`, `proxy-connect-timeout`: 600s
- `proxy-buffering: "off"`

No separate Nginx container is needed; the ingress controller is the proxy.
