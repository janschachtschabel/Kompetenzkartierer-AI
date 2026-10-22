"""`python -m app.core.storage_bucket` makes the configured bucket where a deployment does not
provide one (Compose with MinIO); T6's object store comes with its bucket, and then this
changes nothing."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

from app.core import storage_bucket, storage_s3
from app.core.storage_bucket import ensure_bucket
from tests.support import FAKE_DATABASE_URL, without_settings_variables

BACKEND = Path(__file__).resolve().parents[2]


def _stubbed(region: str) -> tuple[Any, Stubber]:
    client = boto3.session.Session().client(
        "s3",
        region_name=region,
        aws_access_key_id="invented",
        aws_secret_access_key="invented",  # noqa: S106 - the stub answers, nothing is sent
    )
    return client, Stubber(client)


@pytest.fixture
def stubbed() -> Iterator[tuple[Any, Stubber]]:
    client, stubber = _stubbed("us-east-1")
    with stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


def test_a_missing_bucket_is_made(stubbed: tuple[Any, Stubber]) -> None:
    client, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
    stubber.add_response("create_bucket", {}, {"Bucket": "kka"})

    assert ensure_bucket(client, "kka") is True


def test_outside_us_east_1_the_bucket_is_made_in_the_client_s_region() -> None:
    # AWS refuses a create_bucket without the region anywhere but in us-east-1
    client, stubber = _stubbed("eu-central-1")
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
    stubber.add_response(
        "create_bucket",
        {},
        {"Bucket": "kka", "CreateBucketConfiguration": {"LocationConstraint": "eu-central-1"}},
    )

    with stubber:
        assert ensure_bucket(client, "kka") is True
    stubber.assert_no_pending_responses()


def test_a_bucket_made_meanwhile_by_another_step_counts_as_there(stubbed: tuple[Any, Stubber]) -> None:
    client, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
    stubber.add_client_error(
        "create_bucket", service_error_code="BucketAlreadyOwnedByYou", http_status_code=409
    )

    assert ensure_bucket(client, "kka") is False


def test_an_existing_bucket_is_left_as_it_is(stubbed: tuple[Any, Stubber]) -> None:
    client, stubber = stubbed
    stubber.add_response("head_bucket", {}, {"Bucket": "kka"})

    assert ensure_bucket(client, "kka") is False


def test_a_refusal_other_than_missing_is_raised(stubbed: tuple[Any, Stubber]) -> None:
    # 403: the bucket may well exist under someone else; making one would only hide the problem
    client, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="403", http_status_code=403)

    with pytest.raises(ClientError, match="403"):
        ensure_bucket(client, "kka")


S3_ENVIRONMENT = {
    "DATABASE_URL": FAKE_DATABASE_URL,
    "STORAGE_BACKEND": "s3",
    "S3_BUCKET": "kka",
    "S3_ENDPOINT_URL": "http://minio:9000",
    "S3_ACCESS_KEY": "invented-access-key",
    "S3_SECRET_KEY": "invented-secret-key",
}


def _main(environment: dict[str, str]) -> int:
    with without_settings_variables(), mock.patch.dict(os.environ, environment):
        return storage_bucket.main()


@pytest.mark.usefixtures("restore_logging")
def test_the_file_system_store_needs_no_bucket(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main({"DATABASE_URL": FAKE_DATABASE_URL}) == 0
    assert "needs no bucket" in capsys.readouterr().err


@pytest.mark.usefixtures("restore_logging")
def test_a_refusal_ends_with_1_and_one_line_without_a_key(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, stubber = _stubbed("us-east-1")
    stubber.add_client_error("head_bucket", service_error_code="403", http_status_code=403)
    monkeypatch.setattr(storage_s3, "s3_client", lambda settings: client)

    with stubber:
        code = _main(S3_ENVIRONMENT)

    lines = capsys.readouterr().err.strip().splitlines()
    assert code == 1
    assert len(lines) == 1 and "bucket not ready" in lines[0]
    assert "invented-access-key" not in lines[0] and "invented-secret-key" not in lines[0]


def test_the_file_system_store_does_not_wait_for_boto3_to_load() -> None:
    # boto3 takes half a second to import; the step ends at once without S3
    check = "import sys, app.core.storage_bucket; sys.exit(1 if 'boto3' in sys.modules else 0)"

    result = subprocess.run([sys.executable, "-c", check], cwd=BACKEND, check=False)  # noqa: S603 - fixed code

    assert result.returncode == 0
