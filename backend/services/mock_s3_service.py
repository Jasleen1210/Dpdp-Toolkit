import os

BASE_DIR = "mock_s3"

def list_files():
    files = []
    for root, _, filenames in os.walk(BASE_DIR):
        for f in filenames:
            files.append(os.path.join(root, f))
    return files

def read_file(path):
    try:
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except:
        return ""