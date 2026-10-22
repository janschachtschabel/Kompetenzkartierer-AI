"""The object store on an S3-compatible service: AWS, or MinIO in Compose and the tests.

It keeps the file system store's contract, with the two exceptions below: a key is checked
before anything is sent, a missing object raises ObjectNotFound - on deleting too, where S3
itself would answer success - and any other refusal of the service is raised as it came.
S3 holds ``a`` and ``a/b`` side by side, which the file system store refuses; keys that never
nest objects behave the same in both. Two differences remain. Deleting asks first, then
deletes: of two processes deleting one object both may succeed, where on a file system one
gets ObjectNotFound - a caller treats deleting as idempotent and counts nothing on its success.
And a missing object reads as 404 only with ``s3:ListBucket`` on the bucket; without it S3
answers 403, which is raised.

Its own module: boto3 takes a noticeable while to import, and a process on the file system
store should not pay for it.
"""

from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.settings import Settings
from app.core.storage import CHUNK_BYTES, ObjectNotFound, ObjectStream, StorageNotConfigured, check_key

# The codes S3 and MinIO answer a missing object with: get_object names it, head_object has no
# body and carries the status only
_MISSING = frozenset({"NoSuchKey", "NotFound", "404"})
# The same for a missing bucket: head_bucket carries the status, the others name it
NO_BUCKET = frozenset({"NoSuchBucket", "NotFound", "404"})
# The most threads asyncio.to_thread runs on (the default executor's min(32, CPUs + 4)): a smaller
# pool would drop and rebuild a connection for each thread beyond it
POOL_CONNECTIONS = 32


class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def check_bucket(self) -> None:
        """StorageNotConfigured unless the bucket exists. A HEAD on an object answers a missing
        bucket with 404 as it does a missing key: exists() and delete() would take a misspelt
        S3_BUCKET for "no such object" on every call."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            if error_code(error) in NO_BUCKET:
                raise StorageNotConfigured(f"the bucket {self.bucket!r} does not exist (S3_BUCKET)") from None
            raise

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=check_key(key), Body=data)

    def get(self, key: str) -> bytes:
        body = self._object(key)["Body"]
        try:
            return bytes(body.read())
        finally:
            body.close()

    def open_stream(self, key: str) -> ObjectStream:
        answer = self._object(key)
        body = answer["Body"]
        size = answer.get("ContentLength")
        return ObjectStream(None if size is None else int(size), body.iter_chunks(CHUNK_BYTES), body.close)

    def _object(self, key: str) -> Any:
        """The service's answer to reading the object, its body still to read and to close."""
        try:
            return self.client.get_object(Bucket=self.bucket, Key=check_key(key))
        except ClientError as error:
            if _missing(error):
                raise ObjectNotFound(key) from None
            raise

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


def error_code(error: ClientError) -> str | None:
    code = error.response.get("Error", {}).get("Code")
    return None if code is None else str(code)


def _missing(error: ClientError) -> bool:
    return error_code(error) in _MISSING


def s3_client(settings: Settings) -> Any:
    """A client for the configured service. Without keys boto3 takes the credentials of its
    standard chain (AWS_* variables, web identity, the instance's role); a service of its own
    (MinIO) is addressed by path, AWS by name. Only S3_ENDPOINT_URL says where the service is:
    boto3 would also follow AWS_ENDPOINT_URL and an endpoint_url in ~/.aws/config."""
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
        # three attempts in all; botocore reads max_attempts as retries after the first
        retries={"mode": "standard", "total_max_attempts": 3},
        max_pool_connections=POOL_CONNECTIONS,
        ignore_configured_endpoint_urls=True,
    )
    return boto3.session.Session().client(
        "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region, config=config, **keys
    )
