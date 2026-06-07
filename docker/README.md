# Docker Configuration

This directory contains all Docker-related configuration files for Automation Hub.

## Files

- **Dockerfile** - Multi-stage Docker build for the application
- **docker-compose.yml** - Main Docker Compose configuration
- **docker-compose.nginx.yml** - Nginx reverse proxy overlay
- **docker-compose.redis.yml** - Redis service overlay
- **.dockerignore** - Files to exclude from Docker build context

## Usage

### Build Docker Image

```bash
docker buildx build -f docker/Dockerfile -t automation-hub:latest --load .
```

The production Dockerfile uses four stages:

1. `python-base`: shared Python runtime configuration.
2. `wheels`: compilers and headers build all Python dependency wheels.
3. `python-deps`: installs those wheels into a clean relocatable prefix.
4. `runtime`: contains only runtime libraries, dependencies, and application code.

The Python version is configurable without editing the Dockerfile:

```bash
docker buildx build \
  --build-arg PYTHON_VERSION=3.11 \
  -f docker/Dockerfile \
  -t automation-hub:latest \
  --load .
```

CI builds both `linux/amd64` and `linux/arm64`; the SQL Server package
repository follows BuildKit's `TARGETARCH` automatically.

### Run with Docker Compose

From the project root:

```bash
cd docker
docker-compose -f docker-compose.yml up -d
```

Or use Makefile from project root:

```bash
make docker-compose-up
make docker-compose-logs
make docker-compose-down
```

### With Nginx Reverse Proxy

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

Or:

```bash
make docker-compose-up-nginx
```

### With Redis

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.redis.yml up -d
```

Or:

```bash
make docker-compose-up-redis
```

### Combined (Nginx + Redis)

```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml -f docker-compose.redis.yml up -d
```

## Environment Variables

Create a `.env` file in the project root (not in `docker/`) with:

```env
SESSION_SECRET=your-secret-key-here
SMTP_USER=your@email.com
SMTP_PASSWORD=your-password
ADMIN_EMAIL=admin@example.com
REDIS_URL=redis://redis:6379/0
```

## Volumes

- `hub-data` - Persistent volume for database and data files
- `./uploads:/app/uploads` - Bind mount for uploaded files

## PSD fonts

The Creative Studio reads fonts recursively from `FONT_DIR` (default:
`/app/fonts` in Docker). The web UI can upload and select fonts for mapped PSD
text layers and text watermarks.

- Supported uploads: `.ttf`, `.otf`, `.ttc`, `.woff`, `.woff2`
- Default upload limit: 20 MB (`MAX_FONT_UPLOAD_MB`)
- Uploaded files are validated with Pillow before they are stored.
- Duplicate files are detected by SHA-256 and are not stored twice.
- The selected font is passed to previews, synchronous jobs, and Celery jobs.
- Docker Compose persists uploaded fonts in the `font-data` volume.

For local Windows development, use both Compose files. The override mounts the
repository's `fonts` directory as writable:

```powershell
docker compose -f docker/docker-compose.yml -f docker/docker-compose.local.yml up --build
```

Do not commit licensed font files. The repository tracks only
`fonts/.gitkeep`; deploy approved fonts through the UI or a protected volume.
- `./outputs:/app/outputs` - Bind mount for processed outputs

## Notes

- The Dockerfile uses multi-stage build for smaller final image
- Context is set to project root (`..`) so all files are available
- Health checks are configured for container monitoring
- See `DEPLOYMENT.md` for detailed deployment instructions
