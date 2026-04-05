import os 
from pymongo import MongoClient
from dotenv import load_dotenv

try:
	import mongomock
except Exception:
	mongomock = None

load_dotenv()
ATLAS_URL = os.getenv("ATLAS_URL")
USE_MOCK_DB = os.getenv("USE_MOCK_DB", "0") == "1"

if USE_MOCK_DB:
	if mongomock is None:
		raise RuntimeError("USE_MOCK_DB=1 requires mongomock package")
	client = mongomock.MongoClient()
else:
	if not ATLAS_URL and mongomock is not None:
		client = mongomock.MongoClient()
	else:
		client = MongoClient(ATLAS_URL, serverSelectionTimeoutMS=5000)

db = client["dpdp_db"]

collection = db["files"]
logs_collection = db["logs"]
devices_collection = db["devices"]
device_tasks_collection = db["device_tasks"]
device_results_collection = db["device_results"]