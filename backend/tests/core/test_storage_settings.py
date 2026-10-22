"""Which store a process opens, from its settings - checked before the first object is written."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.storage import FileSystemStorage, StorageNotConfigured, open_storage
from app.core.storage_s3 import S3Storage
from tests.support import make_settings


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


def test_the_s3_store_opens_with_its_bucket() -> None:
    settings = make_settings(
        storage_backend="s3",
        s3_bucket="kka",
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key="invented-key",
        s3_secret_key="invented-secret",  # noqa: S106 - invented
    )

    storage = open_storage(settings)

    assert isinstance(storage, S3Storage)
    assert storage.bucket == "kka"


def test_the_s3_store_needs_a_bucket() -> None:
    with pytest.raises(ValidationError, match="s3_bucket"):
        make_settings(storage_backend="s3")


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
