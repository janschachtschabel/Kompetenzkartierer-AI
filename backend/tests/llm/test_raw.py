"""A run's model answers kept as they came, before anything reads them (plan M1 5.3, Gesamtplan
§5): ``runs/<run>/<stage>/<n>.json``, numbered in their order, none ever written over."""

import asyncio
import uuid
from pathlib import Path

import pytest

from app.core.storage import FileSystemStorage
from app.llm.raw import RawResponses

pytestmark = pytest.mark.anyio

RUN = uuid.UUID("01a16940-29e3-7bf4-86d3-421b72698f8e")


async def test_a_run_s_answers_are_kept_in_their_order(tmp_path: Path) -> None:
    storage = FileSystemStorage(tmp_path)
    raw = RawResponses(storage, RUN, "x4")

    first = await raw.keep(b'[{"parts": []}]')
    second = await raw.keep(b"[]")

    assert (first, second) == (f"runs/{RUN}/x4/1.json", f"runs/{RUN}/x4/2.json")
    assert storage.get(first) == b'[{"parts": []}]'


async def test_answers_kept_before_are_written_over_never(tmp_path: Path) -> None:
    # a job asked again after a crash keeps its run: what it kept stays, gaps and all
    storage = FileSystemStorage(tmp_path)
    for n in (1, 2, 4):
        storage.put(f"runs/{RUN}/x4/{n}.json", b"old")

    raw = RawResponses(storage, RUN, "x4")
    kept = [await raw.keep(b"new") for _ in range(3)]

    assert kept == [f"runs/{RUN}/x4/{n}.json" for n in (3, 5, 6)]
    assert storage.get(f"runs/{RUN}/x4/4.json") == b"old"


async def test_answers_kept_side_by_side_take_numbers_of_their_own(tmp_path: Path) -> None:
    raw = RawResponses(FileSystemStorage(tmp_path), RUN, "x4")

    kept = await asyncio.gather(*(raw.keep(str(n).encode()) for n in range(10)))

    assert sorted(kept) == sorted(f"runs/{RUN}/x4/{n}.json" for n in range(1, 11))


@pytest.mark.parametrize("stage", ["X4", "x4/../x5", "", "x" * 20])
def test_a_stage_is_named_as_the_core_s_stages_are(tmp_path: Path, stage: str) -> None:
    with pytest.raises(ValueError, match="stage"):
        RawResponses(FileSystemStorage(tmp_path), RUN, stage)
