from fastapi import APIRouter

from .devices import router as devices_router
from .tasks import router as tasks_router
from .installer import router as installer_router

router = APIRouter()

router.include_router(devices_router)
router.include_router(tasks_router)
router.include_router(installer_router)

@router.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

@router.get("/health")
async def health():
    return {"status": "ok"}