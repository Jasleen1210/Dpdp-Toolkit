import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

try:
    from backend.api.cloud.api_s3 import router as cloud_router
except Exception as exc:
    cloud_router = None
    logging.warning("Cloud router disabled: %s", exc)

try:
    from backend.api.db_api.routes import router as database_router
except Exception as exc:
    database_router = None
    logging.warning("Database router disabled: %s", exc)

from backend.api.agents.app import router as agent_router
from backend.api.identity.auth_org import router as identity_router

app = FastAPI()

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://dpdp-toolkit.vercel.app/,http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173,https://dpdp-toolkit.vercel.app",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    """Health check endpoint to wake Render instance on startup."""
    return {"status": "ok"}

if cloud_router is not None:
    app.include_router(cloud_router)

if database_router is not None:
    app.include_router(database_router)

app.include_router(agent_router)
app.include_router(identity_router)
