import os
from dotenv import load_dotenv

load_dotenv()

ATLAS_URL = os.getenv("ATLAS_URL", "").strip()

if ATLAS_URL:
    from pymongo import MongoClient

    client = MongoClient(ATLAS_URL)
else:
    import mongomock

    client = mongomock.MongoClient()

db = client["cloud_db"]

collection = db["cloud_classification"]
requests_collection = db["user_requests"]
logs_collection = db["cloud_logs"]
