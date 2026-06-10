# VM deployment

The files in `deploy/proxy` configure the internal HTTP proxy for APT, shell
commands, and the Docker daemon. Proxy values are deployment settings and are
not baked into the application image.

Install the proxy configuration:

```bash
sudo install -m 0644 deploy/proxy/100proxy /etc/apt/apt.conf.d/100proxy
sudo install -m 0644 deploy/proxy/profile-proxy.sh /etc/profile.d/proxy.sh
sudo install -d /etc/systemd/system/docker.service.d
sudo install -m 0644 deploy/proxy/docker-proxy.conf \
  /etc/systemd/system/docker.service.d/http-proxy.conf
sudo systemctl daemon-reload
sudo systemctl restart docker
```

For image builds:

```bash
docker compose -f docker/docker-compose.yml build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY"
```
