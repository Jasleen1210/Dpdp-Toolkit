from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


MOCK_CLOUD_SOURCES = [
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


def list_mock_objects(org_id: str | None = None):
    objects = []

    # Built-in static mock sources (shared demo data, not org-specific)
    for source in MOCK_CLOUD_SOURCES:
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

    # Dynamic connected cloud sources stored in backend/cloud_connected/<org_id>,
    # scoped per organisation so one org's connections never leak into another's scans.
    connected_root = BASE_DIR / "cloud_connected"
    if org_id:
        connected_root = connected_root / org_id
    if connected_root.exists():
        for path in connected_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(connected_root)
            parts = rel.parts
            provider_name = parts[0].replace("_", " ").title() if len(parts) > 0 else "Cloud Storage"
            bucket_name = parts[1] if len(parts) > 1 else "default-container"
            object_key = "/".join(parts[2:]) if len(parts) > 2 else path.name

            objects.append(
                {
                    "file": str(path),
                    "platform": "cloud",
                    "provider": f"{provider_name}",
                    "bucket": f"cloud://{bucket_name}",
                    "region": "connected",
                    "location": f"Connected ({provider_name})",
                    "object_key": object_key,
                    "size_bytes": path.stat().st_size,
                }
            )

    return objects


def read_mock_file(path):

    try:
        return Path(path).read_text(errors="ignore")

    except Exception:
        return ""


def write_mock_file(path, content):

    Path(path).write_text(
        content,
        encoding="utf-8"
    )


def get_mock_object_metadata(path):

    normalized = Path(path).resolve()

    for obj in list_mock_objects():

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