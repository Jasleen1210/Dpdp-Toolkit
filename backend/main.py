import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

try:
    from backend.api.cloud_api.api_s3 import router as cloud_router
except Exception as exc:
    cloud_router = None
    logging.warning("Cloud router disabled: %s", exc)

from backend.api.local.app import router as local_router
from backend.api.combined.auth_org import router as auth_org_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if cloud_router is not None:
    app.include_router(cloud_router)

app.include_router(local_router)
app.include_router(auth_org_router)
