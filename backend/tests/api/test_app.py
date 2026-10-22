"""What the API opens as it starts: its database pool and its object store.

Without a usable store the API does not start, naming the setting: an upload that fails later
would cost the caller the file. Opening the store may ask the service (S3's head_bucket), so it
runs in a thread, not in the loop.
"""

import asyncio
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.stub import Stubber  # type: ignore[import-untyped]
from fastapi.testclient import TestClient

from app.api import app as app_module
from app.api.app import create_app
from app.core import storage_s3
from app.core.settings import Settings
from app.core.storage import FileSystemStorage, Storage, StorageNotConfigured
from app.core.storage_async import AsyncStorage
from tests.support import loop_watch, make_settings

SLOW_S = 0.4


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine, loop_factory=asyncio.SelectorEventLoop)


def test_the_app_opens_its_store(tmp_path: Path) -> None:
    app = create_app(make_settings(storage_dir=tmp_path))

    with TestClient(app):
        storage = app.state.storage

    assert isinstance(storage, AsyncStorage)
    assert isinstance(storage.sync, FileSystemStorage)
    assert storage.sync.root == tmp_path.resolve()


def test_without_a_folder_for_its_store_the_app_does_not_start() -> None:
    app = create_app(make_settings(storage_dir=None))

    with pytest.raises(StorageNotConfigured, match="STORAGE_DIR"), TestClient(app):
        pass


def test_without_its_bucket_the_app_does_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    client = boto3.session.Session().client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="invented",
        aws_secret_access_key="invented",  # noqa: S106 - the stub answers, nothing is sent
    )
    monkeypatch.setattr(storage_s3, "s3_client", lambda settings: client)
    app = create_app(
        make_settings(storage_backend="s3", s3_bucket="kka", s3_endpoint_url="http://minio:9000")
    )

    with Stubber(client) as stubber:
        stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
        with pytest.raises(StorageNotConfigured, match="S3_BUCKET"), TestClient(app):
            pass


def test_opening_the_store_does_not_hold_the_loop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def slow_open(settings: Settings) -> Storage:
        time.sleep(SLOW_S)
        return FileSystemStorage(tmp_path)

    monkeypatch.setattr(app_module, "open_storage", slow_open)
    app = create_app(make_settings())

    async def start() -> float:
        async with loop_watch() as longest, app.router.lifespan_context(app):
            pass
        return longest[0]

    assert run(start()) < SLOW_S / 2
