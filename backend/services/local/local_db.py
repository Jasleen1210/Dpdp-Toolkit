import os 
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
ATLAS_URL = os.getenv("ATLAS_URL")

client = MongoClient(ATLAS_URL)

# change name here :) 
db = client["dpdp_db"]

devices_collection = db["devices"]
device_tasks_collection = db["device_tasks"]
device_results_collection = db["device_results"]