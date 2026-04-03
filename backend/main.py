from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel


from datetime import datetime

from services.mock_s3_service import list_files, read_file
from db import collection, logs_collection
from services.detector import detect_pii_full

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Convert PII → flags
def get_pii_flags(pii_result):
    pii_flags = {
        "Name": False,
        "Phone": False,
        "Email": False,
        "Credit Card": False,
        "Aadhaar": False,
        "PAN": False,
        "IP Address": False
    }

    for item in pii_result:
        pii_flags[item["type"]] = True

    return pii_flags


# comapany forwards requests from users to us, for now ive added some mock query here seedha 
requests_db = [
    {
        "id": 1,
        "user": "rahul@gmail.com",
        "type": "DELETE",
        "status": "PENDING"
    }
]

@app.get("/requests")
def get_requests():
    formatted = []

    for r in requests_db:
        formatted.append({
            "id": f"DSR-{r['id']}",
            "type": r["type"].lower(),  # IMPORTANT
            "subject": r["user"],
            "status": r["status"].lower(),
            "sla_remaining": "48h",
            "handler": "auto-system",
            "created": datetime.now().strftime("%Y-%m-%d")
        })

    return {"requests": formatted}

# process request
@app.post("/dpdp/request")
async def handle_request(req: dict):

    req_type = req.get("type")
    identifier = req.get("identifier")

    new_req = {
        "id": len(requests_db) + 1,
        "user": identifier,
        "type": req_type,
        "status": "IN_PROGRESS"
    }

    requests_db.append(new_req)

    # Process immediately for now
    if req_type == "DELETE":
        count = delete_data(identifier)
    elif req_type == "ACCESS":
        files = access_data(identifier)
    elif req_type == "UPDATE":
        count = update_data(identifier, req.get("new_value"))

    new_req["status"] = "COMPLETED"

    return {"message": "Request processed"}


# Scan entire cloud (mock S3)
@app.post("/scan-cloud")
async def scan_cloud():
    files = list_files()
    results = []

    for path in files:
        content = read_file(path)

        file_data = {
            "file": path,
            "content": content
        }

        pii_result = detect_pii_full(file_data)["pii"]
        pii_flags = get_pii_flags(pii_result)

        doc = {
            "file": path,
            "pii": pii_flags
        }

        # Store in MongoDB (UPSERT)
        collection.update_one(
            {"file": path},
            {"$set": doc},
            upsert=True
        )
        results.append(doc)

    return {
        "message": "Cloud scanned successfully",
        "total_files": len(results),
        "results": results
    }


# Get all scanned results
@app.get("/results")
async def get_results():
    data = list(collection.find({}, {"_id": 0}))
    return {"results": data}


# Search user data (DPDP use-case)
class SearchRequest(BaseModel):
    query: str  # email / phone / name

@app.post("/search")
async def search_data(req: SearchRequest):
    query = req.query.lower()
    matched_files = []

    files = list_files()

    for path in files:
        content = read_file(path).lower()

        if query in content:
            pii_result = detect_pii_full({
                "file": path,
                "content": content
            })["pii"]

            pii_flags = get_pii_flags(pii_result)

            matched_files.append({
                "file": path,
                "pii": pii_flags
            })

    return {
        "query": req.query,
        "matches": matched_files
    }

# Health check
@app.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

# ACTION ENGINE
def find_matching_files(identifier):
    matches = []

    files = list_files()

    for path in files:
        content = read_file(path).lower()
        if identifier.lower() in content:
            matches.append(path)

    return matches


def delete_data(identifier):
    files = find_matching_files(identifier)

    # simulate delete (remove from DB only for now)
    for f in files:
        collection.delete_one({"file": f})

    logs_collection.insert_one({
        "request_type": "DELETE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)


def access_data(identifier):
    files = find_matching_files(identifier)

    logs_collection.insert_one({
        "request_type": "ACCESS",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return files


def update_data(identifier, new_value):
    files = find_matching_files(identifier)

    # simulate update (just log for now)
    logs_collection.insert_one({
        "request_type": "UPDATE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)

# Logs
@app.get("/logs")
async def get_logs():
    logs = list(logs_collection.find({}, {"_id": 0}))
    return {"logs": logs}