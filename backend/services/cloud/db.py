import os 
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
ATLAS_URL = os.getenv("ATLAS_URL")
client = MongoClient(ATLAS_URL)

db = client["dpdp_db"]

collection = db["files"]
logs_collection = db["logs"]