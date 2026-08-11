import os

from dotenv import load_dotenv

load_dotenv()


def _use_mock_db() -> bool:
    return os.getenv("USE_MOCK_DB", "").strip() == "1"


def _make_client():
    if _use_mock_db():
        import mongomock

        return mongomock.MongoClient()

    atlas_url = os.getenv("ATLAS_URL", "").strip()
    if not atlas_url:
        raise RuntimeError("ATLAS_URL is required when USE_MOCK_DB != 1")

    from pymongo import MongoClient

    return MongoClient(atlas_url)


client = _make_client()

db = client["dpdp_combined_db"]

users_collection = db["users"]
organizations_collection = db["organizations"]
org_memberships_collection = db["org_memberships"]
sessions_collection = db["sessions"]


def ensure_seed_data() -> None:
    if not _use_mock_db():
        return

    org_id = os.getenv("ORG_ID", "dpdp-org").strip()
    if not org_id:
        return

    existing = organizations_collection.find_one({"id": org_id}, {"_id": 0})
    if existing:
        return

    organizations_collection.insert_one(
        {
            "id": org_id,
            "name": "DPDP Org",
            "agent_token": os.getenv("DEVICE_SHARED_TOKEN", "password123"),
            "admin_api_key": os.getenv("ADMIN_API_KEY", "admin123"),
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )


ensure_seed_data()
