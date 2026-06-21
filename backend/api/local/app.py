# app.py or main.py
from fastapi import FastAPI
from .devices import router as devices_router
from .tasks import router as tasks_router
from .installer import router as installer_router

app = FastAPI()

app.include_router(devices_router)
app.include_router(tasks_router)
app.include_router(installer_router)

@app.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

@app.get("/health")
async def health():
    return {"status": "ok"}