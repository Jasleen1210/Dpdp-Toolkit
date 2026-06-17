from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

CLOUD_SOURCES = [
    {
        "platform": "aws",
        "provider": "AWS S3",
        "root": BASE_DIR / "mock_s3",
        "bucket": "s3://dpdp-prod-data-lake",
        "region": "ap-south-1",
        "location": "Mumbai, India",
    },
    {
        "platform": "gcp",
        "provider": "GCP Cloud Storage",
        "root": BASE_DIR / "mock_gcp",
        "bucket": "gs://dpdp-analytics-archive",
        "region": "asia-south1",
        "location": "Mumbai, India",
    },
    {
        "platform": "azure",
        "provider": "Azure Blob Storage",
        "root": BASE_DIR / "mock_azure",
        "bucket": "azure://dpdp-compliance-container",
        "region": "centralindia",
        "location": "Pune, India",
    },
]


def list_cloud_objects():
    objects = []

    for source in CLOUD_SOURCES:
        root = source["root"]
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            object_key = path.relative_to(root).as_posix()
            objects.append(
                {
                    "file": str(path),
                    "platform": source["platform"],
                    "provider": source["provider"],
                    "bucket": source["bucket"],
                    "region": source["region"],
                    "location": source["location"],
                    "object_key": object_key,
                    "size_bytes": path.stat().st_size,
                }
            )

    return objects


def list_files():
    return [obj["file"] for obj in list_cloud_objects()]


def get_object_metadata(path):
    normalized = Path(path).resolve()

    for obj in list_cloud_objects():
        if Path(obj["file"]).resolve() == normalized:
            return obj

    return {
        "file": str(path),
        "platform": "unknown",
        "provider": "Unknown",
        "bucket": "unknown",
        "region": "unknown",
        "location": "unknown",
        "object_key": Path(path).name,
        "size_bytes": 0,
    }


def read_file(path):
    try:
        return Path(path).read_text(errors="ignore")
    except Exception:
        return ""


def write_file(path, content):
    Path(path).write_text(content)
