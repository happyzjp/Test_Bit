from fastapi import APIRouter
from kokoro.website_admin.api import tasks, auth, roles, menus

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(menus.router, prefix="/menus", tags=["menus"])

