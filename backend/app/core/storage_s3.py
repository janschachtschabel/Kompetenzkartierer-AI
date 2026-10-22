"""The object store on an S3-compatible service: AWS, or MinIO in Compose and the tests.

It keeps the file system store's contract, so no caller can tell them apart: a key is checked
before anything is sent, a missing object raises ObjectNotFound - on deleting too, where S3
itself would answer success - and any other refusal of the service is raised as it came.
S3 holds ``a`` and ``a/b`` side by side, which the file system store refuses; keys that never
nest objects behave the same in both.

Its own module: boto3 takes a noticeable while to import, and a process on the file system
store should not pay for it.
"""

from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.settings import Settings
from app.core.storage import ObjectNotFound, check_key

# The codes S3 and MinIO answer a missing object with: get_object names it, head_object has no
# body and carries the status only
_MISSING = frozenset({"NoSuchKey", "NotFound", "404"})


class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=check_key(key), Body=data)

    def get(self, key: str) -> bytes:
        try:
            answer = self.client.get_object(Bucket=self.bucket, Key=check_key(key))
        except ClientError as error:
            if _missing(error):
                raise ObjectNotFound(key) from None
            raise
        body = answer["Body"]
        try:
            return bytes(body.read())
        finally:
            body.close()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=check_key(key))
        except ClientError as error:
            if _missing(error):
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        # S3 deletes a missing key without a word; the contract says ObjectNotFound
        if not self.exists(key):
            raise ObjectNotFound(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)


def _missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in _MISSING


def s3_client(settings: Settings) -> Any:
    """A client for the configured service. Without keys boto3 takes the credentials of the pod
    or machine (an IAM role); a service of its own (MinIO) is addressed by path, AWS by name."""
    keys: dict[str, str] = {}
    if settings.s3_access_key is not None and settings.s3_secret_key is not None:
        keys = {
            "aws_access_key_id": settings.s3_access_key.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_key.get_secret_value(),
        }
    config = Config(
        s3={"addressing_style": "path" if settings.s3_endpoint_url else "auto"},
        connect_timeout=5,
        read_timeout=60,
        retries={"mode": "standard", "max_attempts": 3},
    )
    return boto3.session.Session().client(
        "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region, config=config, **keys
    )
