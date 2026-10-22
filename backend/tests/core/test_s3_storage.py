"""The S3 store answers like the file system one: the callers must not tell them apart.

botocore's Stubber stands in for the service, so these run without a network; the same calls
run against MinIO in test_s3_integration.py.
"""

from collections.abc import Iterator
from io import BytesIO

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

from app.core.storage import InvalidKey, ObjectNotFound
from app.core.storage_s3 import S3Storage

BUCKET = "kka-test"


@pytest.fixture
def stubbed() -> Iterator[tuple[S3Storage, Stubber]]:
    client = boto3.session.Session().client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="invented",
        aws_secret_access_key="invented",  # noqa: S106 - the stub answers, nothing is sent
    )
    with Stubber(client) as stubber:
        yield S3Storage(client, BUCKET), stubber
        stubber.assert_no_pending_responses()


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(BytesIO(data), len(data))


def test_an_object_is_written_under_its_key(stubbed: tuple[S3Storage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "sources/ab.pdf", "Body": b"%PDF"})

    storage.put("sources/ab.pdf", b"%PDF")


def test_an_object_is_read_back(stubbed: tuple[S3Storage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("get_object", {"Body": _body(b"%PDF")}, {"Bucket": BUCKET, "Key": "sources/ab.pdf"})

    assert storage.get("sources/ab.pdf") == b"%PDF"


def test_a_missing_object_is_not_found_on_reading(stubbed: tuple[S3Storage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    with pytest.raises(ObjectNotFound):
        storage.get("sources/missing.pdf")


def test_exists_asks_for_the_head_only(stubbed: tuple[S3Storage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("head_object", {}, {"Bucket": BUCKET, "Key": "a.json"})
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)

    assert storage.exists("a.json") is True
    assert storage.exists("b.json") is False


def test_deleting_a_missing_object_is_not_found_as_on_a_file_system(
    stubbed: tuple[S3Storage, Stubber],
) -> None:
    # S3 deletes a missing key without complaint; the file system store raises, and callers
    # rely on one contract
    storage, stubber = stubbed
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)

    with pytest.raises(ObjectNotFound):
        storage.delete("gone.json")


def test_an_existing_object_is_deleted(stubbed: tuple[S3Storage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("head_object", {}, {"Bucket": BUCKET, "Key": "a.json"})
    stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": "a.json"})

    storage.delete("a.json")


def test_any_other_service_error_is_raised_not_taken_for_a_missing_object(
    stubbed: tuple[S3Storage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_object", service_error_code="403", http_status_code=403)

    with pytest.raises(Exception, match="403") as raised:
        storage.exists("a.json")
    assert not isinstance(raised.value, ObjectNotFound)


@pytest.mark.parametrize("key", ["../etc/passwd", "a//b", "", "a/./b", "CON", "x" * 600])
def test_a_key_is_checked_before_anything_is_sent(stubbed: tuple[S3Storage, Stubber], key: str) -> None:
    storage, _ = stubbed  # no response queued: a call would fail the stub

    with pytest.raises(InvalidKey):
        storage.put(key, b"data")
