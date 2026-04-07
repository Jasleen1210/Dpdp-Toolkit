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


def _local_db_name() -> str:
	return os.getenv("LOCAL_DB_NAME", "dpdp_local_db").strip() or "dpdp_local_db"


client = _make_client()

db = client[_local_db_name()]

devices_collection = db["devices"]
device_tasks_collection = db["device_tasks"]
device_results_collection = db["device_results"]
device_approval_requests_collection = db["device_approval_requests"]