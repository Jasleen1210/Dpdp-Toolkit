import json
import csv
import os

def get_all_files(folder_path):
    file_paths = []

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            full_path = os.path.join(root, file)
            file_paths.append(full_path)

    return file_paths

def extract_content(file_path, file_type):
    try:
    
        if file_type == "txt":
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        elif file_type == "csv":
            content = ""
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                for row in reader:
                    content += " ".join(row) + "\n"
            return content

        elif file_type == "json":
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                return json.dumps(data)

        else:
            return None

    except Exception as e:
        return f"ERROR: {str(e)}"

def get_file_type(file_path):
    return file_path.split('.')[-1].lower()