"""API and worker refuse a language model setting the model cannot take, or a model layer that
could not count its tokens, before they start work."""

import io
import os
import sys
from pathlib import Path
from unittest import mock

import pytest
from uvicorn.config import STARTUP_FAILURE

from app import serve
from app.jobs import worker
from app.llm import budget
from tests.support import FAKE_DATABASE_URL, FAKE_PEPPER, without_settings_variables

BASE = {"DATABASE_URL": FAKE_DATABASE_URL, "API_KEY_PEPPER": FAKE_PEPPER}
# gpt-6-luna reasons from none to max, not at minimal: a paid job would end in a 400
REFUSED = BASE | {"OPENAI_REASONING_EFFORT": "minimal"}


@pytest.mark.parametrize(
    ("environment", "says"),
    [
        ({}, "o200k_base.tiktoken"),  # without the encoding's file: nothing to count with
        ({"LLM_CONTEXT_TOKENS": "16000"}, "LLM_CONTEXT_TOKENS=16000"),
        ({"LLM_CONTEXT_TOKENS": "32000"}, "LLM_MAX_OUTPUT_TOKENS=16000"),
    ],
    ids=["no-encoding", "context-window", "answer-cap"],
)
def test_api_and_worker_refuse_a_model_layer_that_cannot_count_or_holds_no_document(
    restore_logging: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: dict[str, str],
    says: str,
) -> None:
    if not environment:
        monkeypatch.setattr(budget, "ENCODING_FILE", tmp_path / "o200k_base.tiktoken")
    budget.encoding.cache_clear()
    log = io.StringIO()
    monkeypatch.setattr(sys, "stdout", log)
    monkeypatch.setattr(serve, "build_server", mock.Mock(side_effect=AssertionError("the server was built")))
    monkeypatch.setattr(worker, "_serve", mock.Mock(side_effect=AssertionError("the worker ran")))

    with without_settings_variables(), mock.patch.dict(os.environ, BASE | environment):
        with pytest.raises(SystemExit) as caught:
            serve.main()
        code = worker.main()

    budget.encoding.cache_clear()
    refusals = [line for line in log.getvalue().splitlines() if "ERROR" in line]
    assert (caught.value.code, code) == (STARTUP_FAILURE, 1)
    assert len(refusals) == 2
    assert all(says in line for line in refusals)


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
