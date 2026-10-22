"""`python -m app.core.storage_bucket` makes the configured bucket where a deployment does not
provide one (Compose with MinIO); T6's object store comes with its bucket, and then this
changes nothing."""

from collections.abc import Iterator

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.stub import Stubber  # type: ignore[import-untyped]

from app.core.storage_bucket import ensure_bucket


@pytest.fixture
def stubbed() -> Iterator[tuple[object, Stubber]]:
    client = boto3.session.Session().client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="invented",
        aws_secret_access_key="invented",  # noqa: S106 - the stub answers, nothing is sent
    )
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


def test_a_missing_bucket_is_made(stubbed: tuple[object, Stubber]) -> None:
    client, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
    stubber.add_response("create_bucket", {}, {"Bucket": "kka"})

    assert ensure_bucket(client, "kka") is True


def test_an_existing_bucket_is_left_as_it_is(stubbed: tuple[object, Stubber]) -> None:
    client, stubber = stubbed
    stubber.add_response("head_bucket", {}, {"Bucket": "kka"})

    assert ensure_bucket(client, "kka") is False


def test_a_refusal_other_than_missing_is_raised(stubbed: tuple[object, Stubber]) -> None:
    # 403: the bucket may well exist under someone else; making one would only hide the problem
    client, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="403", http_status_code=403)

    with pytest.raises(Exception, match="403"):
        ensure_bucket(client, "kka")
