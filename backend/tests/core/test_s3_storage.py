"""The S3 store answers like the file system one: the callers must not tell them apart.

botocore's Stubber stands in for the service, so these run without a network; the same calls
run against MinIO in test_s3_integration.py.
"""

from collections.abc import Callable, Iterator
from io import BytesIO
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

from app.core.storage import InvalidKey, ObjectNotFound
from app.core.storage_s3 import S3Storage, s3_client
from tests.support import make_settings

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

    with pytest.raises(ClientError, match="403"):
        storage.exists("a.json")


def test_reading_closes_the_answer_s_body(stubbed: tuple[S3Storage, Stubber]) -> None:
    # an open body holds its pooled connection
    storage, stubber = stubbed
    body = _body(b"%PDF")
    stubber.add_response("get_object", {"Body": body}, {"Bucket": BUCKET, "Key": "a.pdf"})

    storage.get("a.pdf")

    assert body._raw_stream.closed


CALLS: dict[str, Callable[[S3Storage, str], object]] = {
    "put": lambda storage, key: storage.put(key, b"data"),
    "get": lambda storage, key: storage.get(key),
    "exists": lambda storage, key: storage.exists(key),
    "delete": lambda storage, key: storage.delete(key),
}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
@pytest.mark.parametrize("key", ["../etc/passwd", "a//b", "", "a/./b", "CON", "x" * 600])
def test_a_key_is_checked_before_anything_is_sent(
    stubbed: tuple[S3Storage, Stubber], call: Callable[[S3Storage, str], object], key: str
) -> None:
    storage, _ = stubbed  # no response queued: a call would fail the stub

    with pytest.raises(InvalidKey):
        call(storage, key)


def _client(**values: object) -> Any:
    defaults: dict[str, object] = {"storage_backend": "s3", "s3_bucket": "kka"}
    return s3_client(make_settings(**{**defaults, **values}))


def test_a_service_of_its_own_is_addressed_by_path_aws_by_name() -> None:
    # MinIO in Compose knows no bucket host names; AWS prefers them
    assert _client(s3_endpoint_url="http://minio:9000").meta.config.s3["addressing_style"] == "path"
    assert _client().meta.config.s3["addressing_style"] == "auto"


def test_the_client_gives_up_in_time() -> None:
    config = _client().meta.config

    assert config.connect_timeout == 5
    assert config.read_timeout == 60
    # three attempts in all; botocore reads max_attempts as retries after the first
    assert config.retries == {"mode": "standard", "total_max_attempts": 3}


def test_the_pool_holds_a_connection_for_each_thread_that_may_store() -> None:
    # asyncio.to_thread runs on the default executor, at most 32 threads; a smaller pool would
    # drop and rebuild a connection for each thread beyond it
    assert _client().meta.config.max_pool_connections == 32


def test_only_s3_endpoint_url_says_where_the_service_is(monkeypatch: pytest.MonkeyPatch) -> None:
    # boto3 would also take AWS_ENDPOINT_URL(_S3) and endpoint_url from ~/.aws/config: a
    # variable the configuration document does not list would move the store elsewhere
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "http://127.0.0.1:1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://127.0.0.1:2")

    assert _client().meta.endpoint_url.endswith(".amazonaws.com")
    assert _client(s3_endpoint_url="http://minio:9000").meta.endpoint_url == "http://minio:9000"


def test_the_configured_keys_sign_the_requests() -> None:
    client = _client(s3_access_key="invented-key", s3_secret_key="invented-secret")  # noqa: S106 - invented

    assert client._request_signer._credentials.access_key == "invented-key"


def test_without_keys_no_credentials_of_the_machine_are_taken() -> None:
    # tests/conftest.py hides AWS_* and ~/.aws: a developer's own keys never sign a test request
    assert _client()._request_signer._credentials is None
