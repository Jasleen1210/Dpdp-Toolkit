import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from botocore.config import Config

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

AWS_REGION = os.getenv("AWS_REGION")
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")

s3_config = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"max_attempts": 1},
)

try:
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION or "eu-north-1",
        config=s3_config,
    )
except Exception:
    s3 = None


def make_s3_uri(object_key):
    return f"s3://{AWS_BUCKET}/{object_key}"


def extract_object_key(path):
    if isinstance(path, str) and path.startswith("s3://"):
        parsed = urlparse(path)
        return parsed.path.lstrip("/")
    return str(path).lstrip("/")


def list_s3_objects():
    if not s3 or not AWS_BUCKET:
        return []

    objects = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=AWS_BUCKET):
            for obj in page.get("Contents", []):
                object_key = obj["Key"]
                if object_key.endswith("/"):
                    continue
                objects.append(
                    {
                        "file": make_s3_uri(object_key),
                        "platform": "aws",
                        "provider": "AWS S3",
                        "bucket": f"s3://{AWS_BUCKET}",
                        "region": AWS_REGION,
                        "location": "Europe (Stockholm)",
                        "object_key": object_key,
                        "size_bytes": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified"),
                    }
                )
    except Exception as e:
        print(f"S3 list_objects error (gracefully skipped): {e}")
        return []

    return objects


def read_s3_file(path):
    if not s3 or not AWS_BUCKET:
        return b""

    object_key = extract_object_key(path)
    try:
        response = s3.get_object(
            Bucket=AWS_BUCKET,
            Key=object_key,
        )
        return response["Body"].read()  # raw bytes — caller handles extraction
    except Exception as e:
        print(f"S3 read error for {object_key}: {e}")
        return b""


def write_s3_file(path, content):
    if not s3 or not AWS_BUCKET:
        return

    object_key = extract_object_key(path)
    if isinstance(content, str):
        content = content.encode("utf-8")

    try:
        s3.put_object(
            Bucket=AWS_BUCKET,
            Key=object_key,
            Body=content,
            ContentType="text/plain",
        )
        print(f"S3 object updated: s3://{AWS_BUCKET}/{object_key}")
    except Exception as e:
        print(f"S3 write error for {object_key}: {e}")


def get_s3_object_metadata(path):
    if not s3 or not AWS_BUCKET:
        return {
            "file": str(path),
            "platform": "aws",
            "provider": "AWS S3",
            "bucket": "s3://unknown",
            "region": AWS_REGION or "global",
            "location": "Cloud",
            "object_key": Path(path).name,
            "size_bytes": 0,
        }

    object_key = extract_object_key(path)
    try:
        response = s3.head_object(
            Bucket=AWS_BUCKET,
            Key=object_key,
        )
        return {
            "file": make_s3_uri(object_key),
            "platform": "aws",
            "provider": "AWS S3",
            "bucket": f"s3://{AWS_BUCKET}",
            "region": AWS_REGION,
            "location": "Europe (Stockholm)",
            "object_key": object_key,
            "size_bytes": response.get("ContentLength", 0),
            "content_type": response.get("ContentType", "application/octet-stream"),
            "last_modified": response.get("LastModified"),
        }
    except Exception as e:
        print(f"S3 metadata error for {object_key}: {e}")
        return {
            "file": make_s3_uri(object_key),
            "platform": "aws",
            "provider": "AWS S3",
            "bucket": f"s3://{AWS_BUCKET}",
            "region": AWS_REGION,
            "location": "Europe (Stockholm)",
            "object_key": object_key,
            "size_bytes": 0,
        }