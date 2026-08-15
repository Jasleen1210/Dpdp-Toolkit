# This part of the code combines mock_cloud_service and s3_service to provide a unified interface for cloud operations. It allows the application to switch between mock (GCP and Azure) and real S3 services
from backend.services.cloud_storage.s3_service import (
    list_s3_objects,
    read_s3_file,
    write_s3_file,
    get_s3_object_metadata,
)

from backend.services.cloud_storage.mock_cloud_service import (
    list_mock_objects,
    read_mock_file,
    write_mock_file,
    get_mock_object_metadata,
)


def list_cloud_objects():

    aws_objects = list_s3_objects()
 
    mock_objects = list_mock_objects()

    return aws_objects + mock_objects


def list_files():

    return [
        obj["file"]
        for obj in list_cloud_objects()
    ]


def read_file(path):

    # REAL AWS S3
    if isinstance(path, str) and path.startswith("s3://"):

        return read_s3_file(path)

    # MOCK GCP / AZURE
    return read_mock_file(path)


def write_file(path, content):

    # REAL AWS S3
    if isinstance(path, str) and path.startswith("s3://"):

        return write_s3_file(
            path,
            content
        )

    # MOCK GCP / AZURE
    return write_mock_file(
        path,
        content
    )


def get_object_metadata(path):

    # REAL AWS S3
    if isinstance(path, str) and path.startswith("s3://"):

        return get_s3_object_metadata(path)

    # MOCK GCP / AZURE
    return get_mock_object_metadata(path)
