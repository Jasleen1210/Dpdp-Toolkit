from detector import detect_pii_full
from extractor import get_all_files, extract_content, get_file_type
import os
import json

def run_scanner(folder_path):
    results = []

    files = get_all_files(folder_path)

    for file_path in files:
        file_type = get_file_type(file_path)
        content = extract_content(file_path, file_type)

        if content is not None:
            file_data = {
                "file": os.path.basename(file_path),
                "path": file_path,
                "type": file_type,
                "content": content
            }

            pii_result = detect_pii_full(file_data)["pii"]

            results.append({
                **file_data,
                "pii": pii_result
            })

    return results  

if __name__ == "__main__":
    folder = "data"
    output = run_scanner(folder)

    os.makedirs("output", exist_ok=True)

    with open("output/result.json", "w") as f:
        json.dump(output, f, indent=4)

    print("Scanning and detection complete!")