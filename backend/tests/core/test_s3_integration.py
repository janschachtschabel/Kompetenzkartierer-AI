"""The S3 store against a real service: MinIO in a container for tests only.

KKA_TEST_S3_URL names it (locally the container kka-test-minio, in CI a step that starts one),
with KKA_TEST_S3_ACCESS_KEY and KKA_TEST_S3_SECRET_KEY - invented credentials of that
container. Each test gets a bucket of its own and leaves nothing behind. Without the variable
the tests are skipped, unless KKA_REQUIRE_S3 or CI is set.
"""

import os
import uuid
from collections.abc import Iterator

import pytest

from app.core.storage import ObjectNotFound
from app.core.storage_s3 import S3Storage, s3_client
from tests.support import make_settings

pytestmark = pytest.mark.s3


@pytest.fixture
def storage() -> Iterator[S3Storage]:
    url = os.environ.get("KKA_TEST_S3_URL")
    if not url:
        if os.environ.get("KKA_REQUIRE_S3") or os.environ.get("CI"):
            pytest.fail("KKA_TEST_S3_URL is not set, but the S3 tests are required")
        pytest.skip("KKA_TEST_S3_URL is not set")
    bucket = f"kka-t-{uuid.uuid4().hex[:12]}"
    settings = make_settings(
        storage_backend="s3",
        s3_endpoint_url=url,
        s3_bucket=bucket,
        s3_access_key=os.environ["KKA_TEST_S3_ACCESS_KEY"],
        s3_secret_key=os.environ["KKA_TEST_S3_SECRET_KEY"],
    )
    client = s3_client(settings)
    client.create_bucket(Bucket=bucket)
    try:
        yield S3Storage(client, bucket)
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=item["Key"])
        client.delete_bucket(Bucket=bucket)


def test_an_object_is_written_read_replaced_and_deleted(storage: S3Storage) -> None:
    storage.put("sources/ab/abc.pdf", b"%PDF-1.7 first")
    assert storage.exists("sources/ab/abc.pdf")
    assert storage.get("sources/ab/abc.pdf") == b"%PDF-1.7 first"

    storage.put("sources/ab/abc.pdf", b"%PDF-1.7 second")
    assert storage.get("sources/ab/abc.pdf") == b"%PDF-1.7 second"

    storage.delete("sources/ab/abc.pdf")
    assert not storage.exists("sources/ab/abc.pdf")


def test_a_missing_object_is_not_found_the_way_the_file_system_store_says_it(storage: S3Storage) -> None:
    with pytest.raises(ObjectNotFound):
        storage.get("runs/missing.json")
    with pytest.raises(ObjectNotFound):
        storage.delete("runs/missing.json")
    assert storage.exists("runs/missing.json") is False


def test_bytes_come_back_as_they_went_in(storage: S3Storage) -> None:
    data = bytes(range(256)) * 4096  # 1 MiB with every byte value

    storage.put("blob.bin", data)

    assert storage.get("blob.bin") == data
