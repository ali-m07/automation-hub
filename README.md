# Servexa (Automation Hub)

Servexa is an internal automation platform built with FastAPI, Jinja2, and vanilla JavaScript. It combines employee feedback workflows, project ticketing, data tools, creative automation, messaging, and platform administration in one deployable service.

## Current Modules

- **Feedback 180**: nominate evaluators, enter required nomination reasons, manager approvals, and evaluation activity.
- **Projects and Helpdesk**: project portals, personal requests, ticket boards, workflow configuration, and comments.
- **Data and Connectors**: spreadsheet-style tables, sharing, permissions, imports, and SQL Server synchronization.
- **Creative Studio**: PSD templates, layer inspection, data-driven rendering, previews, background jobs, and downloads.
- **Messaging**: SMTP configuration, bulk email campaigns, attachments, and delivery jobs.
- **Process Designer**: roles, groups, workflows, and process access management.
- **Administration**: users, module access, LDAP, notifications, upload limits, connectors, tickets, audit logs, webhooks, SMTP, and diagnostics.

## Feedback Workflow

Users with the `feedback_180` or `feedback` module, plus all admins, can access Feedback.

1. Open `/feedback/nominate`.
2. Search the employee roster by email. Results display `EFullName` when available.
3. Select results using the mouse or `ArrowUp`, `ArrowDown`, and `Enter`.
4. Enter a required reason for every evaluator.
5. Submit the nomination to the manager.

Unsubmitted evaluator selections are stored as a per-user browser draft and survive refreshes. Submitted nominations and their reasons are stored in the `feedback_evaluator_nominations` SQLite table. Existing legacy JSON nominations are migrated automatically.

Feedback routes:

- `/feedback` - evaluation dashboard
- `/feedback/nominate` - evaluator nomination
- `/feedback/nomination-approvals` - manager approval queue

## Authentication

Servexa supports:

- Local session authentication
- Optional TOTP two-factor authentication
- Active Directory / LDAP with multiple domain-controller failover
- Optional OIDC / Keycloak
- Automatic local provisioning only after a successful external login
- Profile synchronization for name, email, and department
- Optional process-group creation from LDAP departments

LDAP can be configured at `/admin/ldap`. Directory searches do not create local users.

## Architecture

```text
app.py
automation_hub/
  core/                  database, auth, settings, Celery, middleware
  routers/               shared page and API routers
  projects/
    feedback/            feedback route exports
    ticketing/           projects, tickets, and feedback handlers
    processes/           process designer
  services/              LDAP/OIDC, employee roster, jobs, connectors
templates/
  base/                  shared application layout and sidebar
  admin/                 routed admin console
  feedback/              feedback and ticketing pages
static/                  CSS and JavaScript
docker/                  production Dockerfile and Compose stack
```

Runtime services in Docker Compose:

- `automation-hub`: FastAPI/uvicorn web application
- `celery-worker`: distributed background worker
- `redis`: broker, result backend, and rate limiting
- `postgres`: shared application data where supported
- SQLite volume: platform settings and compatibility stores

## Requirements

- Python 3.11
- SQL Server ODBC Driver 18 when using employee roster or DB connectors
- Docker and Docker Compose for the recommended deployment
- Redis and PostgreSQL are included in the Compose stack

## Local Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from `.env.example`, then set at minimum:

```env
ENVIRONMENT=development
SESSION_SECRET=replace-with-a-long-random-secret
APP_DATA_DIR=./data
```

Run:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`.

## Docker Deployment

```bash
copy .env.example .env
# Edit SESSION_SECRET and POSTGRES_PASSWORD
docker compose -f docker/docker-compose.yml up -d --build
```

Health endpoints:

- `/health`
- `/live`
- `/ready`

Check services:

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f automation-hub
```

## Important Environment Variables

| Variable | Purpose |
| --- | --- |
| `SESSION_SECRET` | Required production session signing secret |
| `APP_DATA_DIR` | SQLite and persistent application-data directory |
| `POSTGRES_DSN` | PostgreSQL connection string |
| `REDIS_URL` | Cache and rate-limiting Redis URL |
| `CELERY_BROKER_URL` | Celery broker |
| `CELERY_RESULT_BACKEND` | Celery result backend |
| `LDAP_ENABLED` | Enables LDAP authentication |
| `LDAP_SERVERS` | Comma-separated domain controllers |
| `LDAP_USER_BASE_DN` | LDAP user search base |
| `LDAP_GROUP_BASE_DN` | LDAP group search base |
| `LDAP_DEPARTMENT_GROUPS_ENABLED` | Creates managed groups from departments |
| `OIDC_ENABLED` | Enables OIDC login |
| `SSO_DEFAULT_MODULES` | Modules assigned to newly provisioned users |

See `.env.example` for the full configuration.

## Quality Checks

The GitHub Actions pipeline uses Python 3.11 and requires Black formatting.

```bash
python -m black --check .
python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
python -m pytest
```

To format locally:

```bash
python -m black .
```

## CI/CD

`.github/workflows/ci-cd.yml`:

- runs formatting, lint, and tests on pushes and pull requests
- builds multi-architecture images
- pushes images to GitHub Container Registry
- supports development and release deployments
- scans built images with Trivy

`.github/workflows/k8s-deploy.yml` provides manual Kubernetes deployments.

## Routes

- `/summary` - workspace overview
- `/projects` - project portal
- `/projects/my-requests` - signed-in user's requests
- `/feedback` - feedback dashboard
- `/admin` - admin overview
- `/admin/ldap` - LDAP configuration and connectivity test
- `/docs` - OpenAPI documentation

## Security Notes

- Never commit real passwords, LDAP bind secrets, SMTP credentials, or session secrets.
- Use HTTPS in production.
- Persist `/app/data`, uploads, outputs, PostgreSQL, and Redis volumes.
- Keep LDAP disabled until network connectivity and bind tests succeed.
