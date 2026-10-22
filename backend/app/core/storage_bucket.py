"""``python -m app.core.storage_bucket``: make the bucket S3_BUCKET names, if it is missing.

For a deployment that brings its own S3 service (Compose with MinIO). An object store run by
others (T6) comes with its bucket, and then this changes nothing. Exit code 0 when the bucket
exists afterwards - or the file system store is configured, which has none -, 1 when the
service refused. Logs go to stderr.
"""

import logging
import sys
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.logging import configure_logging
from app.core.settings import Settings
from app.core.storage_s3 import NO_BUCKET, error_code, s3_client

log = logging.getLogger("app.core.storage_bucket")  # also when run as __main__


def ensure_bucket(client: Any, bucket: str) -> bool:
    """Make ``bucket`` in the client's region unless it exists; True when it was made. Any refusal
    other than "no such bucket" is raised: a 403 may mean the bucket exists under another owner."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as error:
        if error_code(error) not in NO_BUCKET:
            raise
    else:
        return False
    region = client.meta.region_name
    # AWS takes a bucket without its region in us-east-1 only
    where = {} if region in (None, "us-east-1") else {"LocationConstraint": region}
    try:
        client.create_bucket(Bucket=bucket, **({"CreateBucketConfiguration": where} if where else {}))
    except ClientError as error:
        if error_code(error) != "BucketAlreadyOwnedByYou":  # made meanwhile by a second run
            raise
        return False
    return True


def main() -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    if settings.storage_backend != "s3":
        log.info("the file system store needs no bucket")
        return 0
    assert settings.s3_bucket is not None  # noqa: S101 - the settings refuse s3 without a bucket
    try:
        made = ensure_bucket(s3_client(settings), settings.s3_bucket)
    # ValueError: an address boto3 takes for no host name ("object_store", with "_")
    except (ClientError, BotoCoreError, ValueError) as error:
        log.error("bucket not ready: %s", " ".join(str(error).split()))
        return 1
    log.info("bucket %s %s", settings.s3_bucket, "made" if made else "exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
