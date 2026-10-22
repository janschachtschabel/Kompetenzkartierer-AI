"""API and worker refuse a language model setting the model cannot take before they start work."""

import io
import os
import sys
from unittest import mock

import pytest
from uvicorn.config import STARTUP_FAILURE

from app import serve
from app.jobs import worker
from tests.support import FAKE_DATABASE_URL, FAKE_PEPPER, without_settings_variables

# gpt-6-luna reasons from none to max, not at minimal: a paid job would end in a 400
REFUSED = {
    "DATABASE_URL": FAKE_DATABASE_URL,
    "API_KEY_PEPPER": FAKE_PEPPER,
    "OPENAI_REASONING_EFFORT": "minimal",
}


def test_the_api_refuses_an_effort_the_model_does_not_take(
    restore_logging: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = io.StringIO()
    monkeypatch.setattr(sys, "stdout", log)
    building = mock.Mock(side_effect=AssertionError("the server was built"))
    monkeypatch.setattr(serve, "build_server", building)

    with (
        without_settings_variables(),
        mock.patch.dict(os.environ, REFUSED),
        pytest.raises(SystemExit) as caught,
    ):
        serve.main()

    assert caught.value.code == STARTUP_FAILURE
    assert "OPENAI_REASONING_EFFORT=minimal" in log.getvalue()
    building.assert_not_called()


def test_the_worker_refuses_an_effort_the_model_does_not_take(
    restore_logging: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = io.StringIO()
    monkeypatch.setattr(sys, "stdout", log)
    serving = mock.Mock(side_effect=AssertionError("the worker ran"))
    monkeypatch.setattr(worker, "_serve", serving)

    with without_settings_variables(), mock.patch.dict(os.environ, REFUSED):
        code = worker.main()

    assert code == 1
    assert "OPENAI_REASONING_EFFORT=minimal" in log.getvalue()
    serving.assert_not_called()
