"""FastAPI Web Application for PSD Processing and Email Sending."""

import os
import logging
import secrets
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from automation_hub.core.db import init_database
from automation_hub.core.middleware import (
    RequestIdAndLogMiddleware,
    setup_structured_logging,
)
from automation_hub.routers import (
    admin_router,
    admin_page_router,
    auth_router,
    auth_page_router,
    profile_router,
    creative_router,
    connectors_router,
    messaging_router,
    downloads_router,
    gallery_router,
    jobs_router,
    health_router,
    pages_router,
    feedback_router,
    processes_router,
    processes_page_router,
)
from automation_hub.routers.data import data_router
from automation_hub.core import pg
from automation_hub.services.psd_processor import PSDProcessor
from automation_hub.services.email_service import EmailService
from automation_hub.services.job_processor import JobProcessor

app = FastAPI(
    title="Servexa",
    version="2.0.0",
    description="""
    Servexa - Intelligent service and process management platform.
    bulk messaging, and creative automation.
    
    ## Features
    
    * **Creative Studio** - Upload PSD templates, map layers to data columns, generate outputs
    * **Data & Connectors** - Spreadsheet-like grid, multiple tables, database sync
    * **Messaging** - Bulk email campaigns with images and attachments
    * **Admin Panel** - User management, audit logs, tickets, notifications
    * **Support** - Ticket system for user assistance
    
    ## Authentication
    
    * Session-based authentication
    * Optional 2FA (TOTP) support
    * Role-based access control (admin/user)
    * Module-based permissions
    """,
    contact={
        "name": "Servexa Support",
        "url": "https://github.com/ali-m07/automation-hub",
    },
    license_info={
        "name": "MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session / auth middleware
SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    if os.getenv("ENVIRONMENT", "production").lower() == "production":
        raise RuntimeError("SESSION_SECRET must be set in production")
    SESSION_SECRET = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Request ID and structured logging middleware
app.add_middleware(RequestIdAndLogMiddleware)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.state.templates = templates  # for routers that need template rendering

# Initialize services
psd_processor = PSDProcessor()
email_service = EmailService()
job_processor = JobProcessor(psd_processor)

# Store services in app state for routers
app.state.psd_processor = psd_processor
app.state.email_service = email_service
app.state.job_processor = job_processor

# Initialize database
init_database()
# Initialize Postgres tables schema for Data Grid (optional)
try:
    pg.init_tables_schema()
except Exception:
    # Don't block app startup if Postgres is not configured
    pass


@app.on_event("startup")
def _on_startup() -> None:
    """Initialize application on startup."""
    setup_structured_logging()
    job_processor.start()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Render error page for 500s with request_id so user can Report to admin. Re-raise HTTPException."""
    if isinstance(exc, HTTPException):
        raise exc
    rid = getattr(request.state, "request_id", None) or ""
    error_msg = str(exc) or "An unexpected error occurred"
    # Debug: log full traceback for sqlite3.Row .get errors so we see exact line
    if (
        isinstance(exc, AttributeError)
        and "sqlite3.Row" in error_msg
        and "get" in error_msg
    ):
        import traceback

        tb = traceback.format_exc()
        logging.getLogger(__name__).error(
            "sqlite3.Row .get error – full traceback:\n%s\npath=%s",
            tb,
            request.url.path,
        )
        print(
            "\n*** sqlite3.Row .get DEBUG – full traceback ***\n"
            + tb
            + "\npath="
            + request.url.path
            + "\n***\n",
            flush=True,
        )
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": error_msg, "request_id": rid},
            status_code=500,
        )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"request": request, "error": error_msg, "request_id": rid},
        status_code=500,
    )


# Include routers
app.include_router(health_router)  # /health, /live, /ready
app.include_router(pages_router)  # /, /error
app.include_router(admin_page_router)  # GET /admin
app.include_router(admin_router)  # /api/admin/*
app.include_router(auth_page_router)  # GET /login
app.include_router(auth_router)  # POST /login, POST /login-2fa, GET /logout
app.include_router(profile_router)  # /api/me/*
app.include_router(
    creative_router
)  # /api/upload-psd, /api/creative/*, /api/preview, /api/process
app.include_router(connectors_router)  # /api/db-connectors/*
app.include_router(data_router)  # /api/data/*
app.include_router(feedback_router)  # /api/feedback/*
app.include_router(processes_page_router)  # GET /process-designer
app.include_router(processes_router)  # /api/processes/*
app.include_router(
    messaging_router
)  # /api/send-emails, /api/test-smtp, /api/upload-image*
app.include_router(downloads_router)  # /api/download/*
app.include_router(gallery_router)  # /api/gallery/*
app.include_router(jobs_router)  # /api/jobs/*


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
