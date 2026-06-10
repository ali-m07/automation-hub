# Automation Hub

**No Photoshop required.** Web application for PSD conversion (psd-tools), data grids, bulk messaging, admin panel, and support tickets. Runs on server/cloud without Adobe Photoshop.

---

## Specifications

### Overview

| Item | Description |
|------|-------------|
| **Name** | Automation Hub |
| **Type** | Web application (FastAPI + Jinja2 + vanilla JS) |
| **PSD processing** | [psd-tools](https://github.com/psd-tools/psd-tools) + Pillow – no Photoshop |
| **Platform** | Windows, macOS, Linux, Docker, Kubernetes |
| **Language** | Backend: Python 3.7+; Frontend: HTML/CSS/JS (English only) |

### Features

Background PSD, bulk-email, and file jobs use Celery + Redis with automatic
retry, persisted progress, per-user status APIs, and cancellation.

The Advanced PSD Layer Editor provides a flattened canvas preview, layer
metadata, fixed or data-driven text replacement, per-layer fonts, uploaded
image replacement, batch rendering, and ZIP downloads.

- **Creative Studio (PSD)** – Upload PSD template + Excel/CSV; map columns to text layers; composite and export PNG/PSD (no Photoshop). **Preview** – first-row sample before full process. **Template library** – save PSDs as named templates and select from list. **Queue** – optional “Process in background” for heavy jobs (in-app queue + worker thread).
- **Data & Connectors** – Spreadsheet-like grid (Tabulator.js), multiple tables, JSON storage, search, copy/paste, share links, per-user permissions (view/edit/view_nocopy). **External database sync**: configure SQL Server connectors in Admin; users with the “Database Connectors” module can upload Excel and sync to the remote table (staging + MERGE). Requires pyodbc and an ODBC driver for SQL Server.
- **Messaging** – Bulk email with images; SMTP config (host, port, user, password); test connection; optional image link per row.
- **Admin panel** – Users (pending/active/inactive), roles (admin/user), module permissions, approve/reject signups, edit user, change email, reset password, logout all sessions, login log, audit log, tickets (reply, status, priority, category), notifications config (signup/ticket/reply emails), dashboard stats.
- **Support** – Users create tickets (subject, body, priority, category); admins reply; email notifications on reply; first response / resolved timestamps.
- **Auth** – Session-based; signup (pending until approved); login; forgot password / reset by token; username = email; strong password rules. **Optional 2FA (TOTP)** – enable per user in Security panel; login then requires 6-digit code (e.g. Google Authenticator).
- **Enterprise auth** – Optional Active Directory/LDAP login and OIDC single sign-on for Keycloak or any standards-compliant provider, with automatic local user provisioning.

### Tech stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI, uvicorn, Python 3.7+ |
| **Templating** | Jinja2 |
| **Frontend** | Vanilla JavaScript, modern CSS, Tabulator.js (grid) |
| **PSD** | psd-tools, Pillow, numpy |
| **Data** | pandas, openpyxl (Excel/CSV); SQLite (users, tables, grants, tickets, audit, notifications); JSON files (grid data) |
| **Auth** | passlib (pbkdf2_sha256), Starlette sessions |
| **Email** | smtplib (built-in) |
| **Deploy** | Docker, Docker Compose, Kubernetes (Kustomize), Helm, GitHub Actions (CI/CD) |

### Requirements (Python)

- `fastapi`, `uvicorn[standard]`, `python-multipart`, `jinja2`, `aiofiles`
- `pandas`, `openpyxl`
- `psd-tools`, `Pillow`, `numpy`
- `passlib`
- See **requirements.txt**. No Adobe Photoshop required.

### Project structure

```
.
├── app.py                  # FastAPI app entry point, includes routers
├── requirements.txt
├── Makefile
├── docker/                 # Docker configuration files
│   ├── Dockerfile
│   ├── docker-compose.yml      # Main compose file
│   ├── docker-compose.nginx.yml # Nginx reverse proxy compose
│   ├── docker-compose.redis.yml # Redis service compose
│   └── .dockerignore
├── automation_hub/          # Core application package (modular structure)
│   ├── __init__.py
│   ├── core/               # Core utilities and shared modules
│   │   ├── __init__.py
│   │   ├── auth.py         # Authentication, authorization, password hashing
│   │   ├── audit.py        # Audit logging
│   │   ├── config.py       # Pydantic Settings for configuration management
│   │   ├── constants.py    # App-wide constants
│   │   ├── db.py           # Database connection, utilities, and initialization
│   │   ├── middleware.py   # Request ID and structured logging middleware
│   │   ├── notifications.py # Email notification helpers and signup notifications
│   │   ├── redis_util.py   # Optional Redis cache/rate limiting (when REDIS_URL is set)
│   │   ├── settings.py     # Settings management and directory paths
│   │   ├── utils.py        # Request utilities (client IP, user agent)
│   │   └── validation.py   # Upload size validation and rate limiting
│   ├── services/           # Reusable service-layer components
│   │   ├── __init__.py     # Service factory functions
│   │   ├── db_connector.py # External DB connector (SQL Server sync via pyodbc)
│   │   ├── email_service.py # SMTP / bulk email + notifications
│   │   ├── job_processor.py # Background job processor for job_queue
│   │   └── psd_processor.py # PSD read/composite (psd-tools + Pillow)
│   ├── routers/            # API route handlers (by domain)
│   │   ├── __init__.py
│   │   ├── admin.py        # Admin panel API endpoints
│   │   ├── auth.py         # Login, logout, 2FA, profile
│   │   ├── creative.py     # PSD processing, templates, preview
│   │   ├── downloads.py    # File download serving
│   │   ├── gallery.py      # User file repository
│   │   ├── health.py       # Health check endpoints (/health, /live, /ready)
│   │   ├── jobs.py         # Background job status polling
│   │   └── pages.py        # Page routes (home, error pages)
│   └── projects/           # Project-oriented router re-exports
│       ├── __init__.py
│       ├── admin/          # Admin domain routers
│       ├── auth/           # Auth domain routers
│       ├── connectors/     # DB connectors domain
│       ├── creative/       # Creative/PSD domain
│       ├── downloads/      # Downloads domain
│       ├── gallery/        # Gallery domain
│       ├── jobs/           # Jobs domain
│       └── messaging/      # Messaging/email domain
├── nginx/                  # Nginx configuration files
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── nginx.docker.conf
│   └── README.md
├── templates/
│   ├── index.html          # Legacy (redirects to /summary)
│   ├── error.html          # Global error page
│   ├── base/
│   │   └── layout.html     # Base template with sidebar, top-nav, panels
│   ├── admin/
│   │   └── admin.html      # Admin panel
│   ├── auth/
│   │   ├── login.html      # Login page
│   │   └── reset_password.html  # Password reset page
│   ├── summary/
│   │   └── index.html      # Summary/dashboard page
│   ├── data/
│   │   ├── index.html      # Data & Connectors page
│   │   └── shared_table.html  # Public share view for a table
│   ├── creative/
│   │   └── index.html      # Creative Studio (Photoshop) page
│   ├── messaging/
│   │   └── index.html      # Messaging/Email campaigns page
│   ├── gallery/
│   │   └── index.html      # File Repository/Gallery page
│   └── support/
│       └── index.html       # Support/Tickets page
├── static/
│   ├── css/                # style.css, tabulator.min.css, etc.
│   └── js/                 # app.js, tabulator.min.js, etc.
├── uploads/                # Uploaded PSD/data (runtime)
├── outputs/                # Processed images (runtime)
├── data_pools/             # JSON grid data (or APP_DATA_DIR)
├── k8s/                    # Kustomize manifests
├── helm/automation-hub/    # Helm chart
└── .github/workflows/      # ci-cd.yml, k8s-deploy.yml
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `SESSION_SECRET` | Secret for session cookie (required in production) |
| `APP_DATA_DIR` | Directory for SQLite DB and data_pools (default: current dir) |
| `ADMIN_EMAIL` | Used for signup/ticket notifications and password reset sender |
| `ADMIN_USER` | Initial administrator username; used only when `ADMIN_PASS` is also set |
| `ADMIN_PASS` | Initial administrator password; required to bootstrap an administrator |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | SMTP for sending emails (optional; can be set in admin UI) |
| `REDIS_URL` | Optional Redis URL for rate limiting and future cache (e.g. `redis://localhost:6379/0`). When set: login limited per IP; upload/process limited per user or IP. When not set, no rate limits. |
| `STRUCTURED_LOGGING` | Set to `1`, `true`, or `yes` to emit JSON logs with `timestamp`, `level`, `message`, `request_id` (and optional `duration_ms`, `path`, `status`) for debugging and monitoring. |
| `ENABLE_2FA` | When set to `1`, `true`, or `yes`, enforce TOTP 2FA on login for users who have 2FA enabled. When unset, 2FA is effectively disabled (useful for local/dev). |

### API overview (main endpoints)

- **Health:** `GET /health`, `GET /live`, `GET /ready` (K8s probes / monitoring)
- **API Docs:** `GET /docs` (Swagger UI), `GET /redoc` (ReDoc), `GET /openapi.json` (OpenAPI schema)
- **Auth:** `GET /`, `/login`, `POST /login`, `POST /login-2fa`, `GET /logout`, `POST /api/signup`, `POST /api/forgot-password`, `POST /api/reset-password`, `GET /api/me`, `GET /api/me/2fa/status`, `POST /api/me/2fa/setup`, `POST /api/me/2fa/verify`, `POST /api/me/2fa/disable`
- **Pages:** `GET /summary`, `GET /data`, `GET /creative`, `GET /messaging`, `GET /gallery`, `GET /support`
- **Admin:** `GET /admin`, `GET /api/admin/users`, `POST /api/admin/users/{username}/approve`, `POST /api/admin/users/{username}/reject`, `POST /api/admin/users/bulk-approve`, `POST /api/admin/users/bulk-reject`, `POST /api/admin/users/{username}/update`, `POST /api/admin/users/{username}/change-email`, `POST /api/admin/users/{username}/reset-password`, `POST /api/admin/users/{username}/logout-all`, `DELETE /api/admin/users/{username}`, `GET /api/admin/audit-log`, `GET /api/admin/stats/summary`, `GET/POST /api/admin/notifications/config`, `POST /api/admin/tickets/{id}/reply`, `POST /api/admin/tickets/{id}/status`
- **Data:** `GET /api/data/tables`, `POST /api/data/tables`, `GET /api/data/grid`, `POST /api/data/grid`, `GET /api/data/tables/{id}/export-excel`, `POST /api/data/tables/{id}/share`, `GET /shared/{token}`
- **Creative:** `POST /api/upload-psd`, `POST /api/upload-data`, `POST /api/process` (optional `?async=1` for queue), `GET /api/jobs/{queue_id}`, `POST /api/preview`, `GET /api/download-preview/{job_id}/{filename}`, `GET/POST/DELETE /api/creative/templates`, `GET /api/creative/templates/{id}/layers`, `GET /api/gallery/files`, `GET /api/gallery/thumb/{id}`, `GET /api/gallery/download/{id}`
- **Messaging:** `POST /api/send-emails`, `POST /api/test-smtp`, `POST /api/upload-image`, `POST /api/upload-image-folder`
- **Tickets:** `POST /api/tickets`, `GET /api/tickets`

### Testing

Run tests with:
```bash
make test          # Run all tests
make test-unit     # Unit tests only
make test-integration  # Integration tests only
make test-cov      # With coverage report
```

See `tests/README.md` for detailed testing documentation.

### Deployment

- **Local:** `pip install -r requirements.txt` then `python app.py` or `uvicorn app:app --host 0.0.0.0 --port 8000`. Open http://localhost:8000
- **Docker:** `docker build -f docker/Dockerfile -t automation-hub .` then run with `SESSION_SECRET`, volumes for `uploads/`, `outputs/`, `/app/data`
- **Docker Compose:** `cd docker && docker-compose -f docker-compose.yml up -d` (optional `.env` for `SESSION_SECRET`, SMTP, `ADMIN_EMAIL`). Optional Redis: `cd docker && docker-compose -f docker-compose.yml -f docker-compose.redis.yml up -d`. Or use `make docker-compose-up`
- **Kubernetes:** `kubectl apply -k k8s/ -n automation-hub` (see **k8s/README.md**, create secrets first)
- **Helm:** `helm upgrade --install automation-hub ./helm/automation-hub -n automation-hub --set secret.sessionSecret=...` (see **helm/automation-hub/README.md**)
- **CI/CD:** GitHub Actions in `.github/workflows/` (ci-cd.yml, k8s-deploy.yml)

Details: **DEPLOYMENT.md**, **docs/QUICKSTART.md**, **docs/README_WEB.md**.

### Optional features (env / config)

| Feature | Env / requirement | Description |
|--------|--------------------|-------------|
| **Rate limiting** | `REDIS_URL` | When Redis is set: login 10/min per IP; upload 30/min and process 20/min per user (or IP if not logged in). 429 when exceeded. |
| **Structured logging** | `STRUCTURED_LOGGING=1` | Logs as JSON with `request_id`, level, message, path, status, duration. Use for log aggregators and tracing. |
| **2FA (TOTP)** | `pyotp` in requirements | Users enable in **Security** (nav). Login then asks for 6-digit code. Disable with current code. |
| **PSD template library** | (built-in) | Save uploaded PSD as template; select from dropdown in Creative Studio. |
| **Preview** | (built-in) | Button “Preview (first row)” before Process to see sample output. |
| **Job queue** | (built-in) | Check “Process in background”; job runs in worker thread; poll `GET /api/jobs/{id}` for result. |


---

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:8000**. Set `ADMIN_USER` and `ADMIN_PASS` before the first startup to bootstrap an administrator.

---

## Links

- **Web app details:** docs/README_WEB.md  
- **Quick start:** docs/QUICKSTART.md  
- **Deploy (Docker/K8s/Helm):** DEPLOYMENT.md  
- **Testing:** tests/README.md  
- **K8s:** k8s/README.md  
- **Helm:** helm/automation-hub/README.md  
- **Docker:** docker/README.md  
