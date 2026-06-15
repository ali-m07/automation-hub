# Re-export existing routers for project-oriented layout.
from automation_hub.routers.auth import (
    auth_router as router,
    page_router as page_router,
    profile_router as profile_router,
    notifications_router as notifications_router,
)
