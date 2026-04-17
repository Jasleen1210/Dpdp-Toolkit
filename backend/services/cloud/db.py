import os 
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
ATLAS_URL = os.getenv("ATLAS_URL")
client = MongoClient(ATLAS_URL)

db = client["cloud_db"]

collection = db["cloud_classification"]
requests_collection = db["user_requests"]
logs_collection = db["cloud_logs"]