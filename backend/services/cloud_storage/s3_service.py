import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

AWS_REGION = os.getenv("AWS_REGION")
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION or "eu-north-1"
)


def make_s3_uri(object_key):

    return f"s3://{AWS_BUCKET}/{object_key}"


def extract_object_key(path):

    if isinstance(path, str) and path.startswith("s3://"):

        parsed = urlparse(path)

        return parsed.path.lstrip("/")

    return str(path).lstrip("/")


def list_s3_objects():

    objects = []

    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=AWS_BUCKET
    ):

        for obj in page.get("Contents", []):

            object_key = obj["Key"]

            # Ignore folder markers
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
                    "size_bytes": obj.get(
                        "Size",
                        0
                    ),
                    "last_modified": obj.get(
                        "LastModified"
                    ),
                }
            )

    return objects


def read_s3_file(path):

    object_key = extract_object_key(path)

    try:

        response = s3.get_object(
            Bucket=AWS_BUCKET,
            Key=object_key
        )

        content = response["Body"].read()

        return content.decode(
            "utf-8",
            errors="ignore"
        )

    except ClientError as e:

        print(
            f"S3 read error for "
            f"{object_key}: {e}"
        )

        return ""


def write_s3_file(path, content):

    object_key = extract_object_key(path)

    if isinstance(content, str):

        content = content.encode("utf-8")

    try:

        s3.put_object(
            Bucket=AWS_BUCKET,
            Key=object_key,
            Body=content,
            ContentType="text/plain"
        )

        print(
            f"S3 object updated: "
            f"s3://{AWS_BUCKET}/{object_key}"
        )

    except ClientError as e:

        print(
            f"S3 write error for "
            f"{object_key}: {e}"
        )

        raise


def get_s3_object_metadata(path):

    object_key = extract_object_key(path)

    try:

        response = s3.head_object(
            Bucket=AWS_BUCKET,
            Key=object_key
        )

        return {
            "file": make_s3_uri(object_key),
            "platform": "aws",
            "provider": "AWS S3",
            "bucket": f"s3://{AWS_BUCKET}",
            "region": AWS_REGION,
            "location": "Europe (Stockholm)",
            "object_key": object_key,
            "size_bytes": response.get(
                "ContentLength",
                0
            ),
            "content_type": response.get(
                "ContentType",
                "application/octet-stream"
            ),
            "last_modified": response.get(
                "LastModified"
            ),
        }

    except ClientError as e:

        print(
            f"S3 metadata error for "
            f"{object_key}: {e}"
        )

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