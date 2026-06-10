from automation_hub.projects.admin.router import (
    router as admin_router,
    page_router as admin_page_router,
)
from automation_hub.projects.auth.router import (
    router as auth_router,
    page_router as auth_page_router,
    profile_router,
)
from automation_hub.projects.creative.router import router as creative_router
from automation_hub.projects.connectors.router import router as connectors_router
from automation_hub.projects.messaging.router import router as messaging_router
from automation_hub.projects.downloads.router import router as downloads_router
from automation_hub.projects.gallery.router import router as gallery_router
from automation_hub.projects.jobs.router import router as jobs_router
from automation_hub.projects.feedback.router import router as feedback_router
from automation_hub.projects.processes.router import (
    router as processes_router,
    page_router as processes_page_router,
)
from automation_hub.routers.health import health_router
from automation_hub.routers.pages import pages_router

__all__ = [
    "admin_router",
    "admin_page_router",
    "auth_router",
    "auth_page_router",
    "profile_router",
    "creative_router",
    "connectors_router",
    "messaging_router",
    "downloads_router",
    "gallery_router",
    "jobs_router",
    "health_router",
    "pages_router",
    "feedback_router",
    "processes_router",
    "processes_page_router",
]
