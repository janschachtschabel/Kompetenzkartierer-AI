"""Which store a process opens, from its settings - checked before the first object is written."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.stub import Stubber  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.core import storage_s3
from app.core.settings import Settings
from app.core.storage import FileSystemStorage, StorageNotConfigured, open_storage
from app.core.storage_s3 import S3Storage, s3_client
from tests.support import FAKE_DATABASE_URL, make_settings, without_settings_variables

S3: dict[str, Any] = {
    "storage_backend": "s3",
    "s3_bucket": "kka",
    "s3_endpoint_url": "http://127.0.0.1:1",
    "s3_access_key": "invented-key",
    "s3_secret_key": "invented-secret",
}


@pytest.fixture
def stubbed_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[Stubber]:
    """open_storage gets a client whose answers the test queues; nothing is sent."""
    client = boto3.session.Session().client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="invented",
        aws_secret_access_key="invented",  # noqa: S106 - the stub answers, nothing is sent
    )
    monkeypatch.setattr(storage_s3, "s3_client", lambda settings: client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def test_the_file_system_is_the_default() -> None:
    settings = make_settings()

    assert settings.storage_backend == "fs"
    assert settings.storage_dir is None


def test_the_file_system_store_opens_in_its_folder(tmp_path: Path) -> None:
    storage = open_storage(make_settings(storage_dir=tmp_path))

    assert isinstance(storage, FileSystemStorage)
    assert storage.root == tmp_path.resolve()


def test_the_file_system_store_needs_its_folder() -> None:
    with pytest.raises(StorageNotConfigured, match="STORAGE_DIR"):
        open_storage(make_settings())


def test_the_s3_store_opens_with_its_bucket(stubbed_client: Stubber) -> None:
    stubbed_client.add_response("head_bucket", {}, {"Bucket": "kka"})

    storage = open_storage(make_settings(**S3))

    assert isinstance(storage, S3Storage)
    assert storage.bucket == "kka"


def test_a_missing_bucket_stops_the_opening(stubbed_client: Stubber) -> None:
    # HEAD on an object answers a missing bucket with 404 as it does a missing key: exists()
    # and delete() would take a misspelt S3_BUCKET for "no such object", every time
    stubbed_client.add_client_error("head_bucket", service_error_code="404", http_status_code=404)

    with pytest.raises(StorageNotConfigured, match="S3_BUCKET"):
        open_storage(make_settings(**S3))


def test_the_s3_store_needs_a_bucket() -> None:
    with pytest.raises(ValidationError, match="s3_bucket"):
        make_settings(storage_backend="s3")


@pytest.mark.parametrize("bucket", ["KKA", "ab", "-kka", "kka-", "kka_x", "k" * 64])
def test_a_bucket_name_follows_the_s3_rules(bucket: str) -> None:
    with pytest.raises(ValidationError, match="s3_bucket"):
        make_settings(storage_backend="s3", s3_bucket=bucket)


@pytest.mark.parametrize("bucket", ["kka", "kka.test-1", "k" * 63])
def test_a_plain_bucket_name_passes(bucket: str) -> None:
    assert make_settings(storage_backend="s3", s3_bucket=bucket).s3_bucket == bucket


def test_an_empty_endpoint_means_aws_itself() -> None:
    # The Helm values leave S3_ENDPOINT_URL empty for AWS; boto3 refuses "" as an address
    with without_settings_variables(), mock.patch.dict(os.environ, {"S3_ENDPOINT_URL": ""}):
        settings = Settings(database_url=FAKE_DATABASE_URL, storage_backend="s3", s3_bucket="kka")

    assert settings.s3_endpoint_url is None
    assert s3_client(settings).meta.endpoint_url.endswith(".amazonaws.com")


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@minio:9000",
        "http://minio:9000/?versions",
        "http://minio:9000/#a",
        "ftp://minio:9000",
        "minio:9000",
        "http://minio:70000",
        "http:///kka",
        # host names boto3 refuses as it builds the client, with the value in its error
        "http://object_store:9000",
        "http://-minio:9000",
        "http://minio-.example:9000",
    ],
)
def test_an_endpoint_is_a_plain_http_address(url: str) -> None:
    # a user or a query would ride along on every request and into the logs
    with pytest.raises(ValidationError, match="s3_endpoint_url") as raised:
        make_settings(**{**S3, "s3_endpoint_url": url})

    assert url not in str(raised.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://minio:9000",
        "http://127.0.0.1:59000",
        "http://[::1]:9000",
        "https://s3.eu-central-1.amazonaws.com",
    ],
)
def test_an_endpoint_boto3_takes_passes(url: str) -> None:
    settings = make_settings(**{**S3, "s3_endpoint_url": url})

    assert s3_client(settings).meta.endpoint_url == url


def test_a_refused_endpoint_is_not_quoted() -> None:
    with pytest.raises(ValidationError) as raised:
        make_settings(**{**S3, "s3_endpoint_url": "http://kka:invented-password@minio:9000"})

    assert "invented-password" not in str(raised.value)


@pytest.mark.parametrize("region", ["", "EU-Central-1", "eu central 1", "eu-central-1\n", "../x", "-eu"])
def test_a_region_is_a_plain_name(region: str) -> None:
    with pytest.raises(ValidationError, match="s3_region"):
        make_settings(s3_region=region)


@pytest.mark.parametrize("region", ["us-east-1", "eu-central-1", "auto", "fr-par", "nyc3"])
def test_the_regions_of_common_services_pass(region: str) -> None:
    assert make_settings(s3_region=region).s3_region == region


def test_the_s3_keys_come_both_or_neither() -> None:
    # one without the other is a typo, not a choice; neither lets boto3 take the pod's role
    with pytest.raises(ValidationError, match="s3_access_key and s3_secret_key"):
        make_settings(storage_backend="s3", s3_bucket="kka", s3_access_key="invented-key")


def test_the_s3_secret_never_shows_in_an_error() -> None:
    with pytest.raises(ValidationError) as raised:
        make_settings(
            storage_backend="s3",
            s3_bucket="kka",
            s3_secret_key="invented-secret-value",  # noqa: S106 - invented
        )

    assert "invented-secret-value" not in str(raised.value)
