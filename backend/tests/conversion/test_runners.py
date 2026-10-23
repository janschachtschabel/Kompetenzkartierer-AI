"""The conversion in a child process: its answer comes back as JSON, and a cancel, a deadline or a
lost lease ends it (plan M1, 3.4)."""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

import pytest

from app.conversion.convert import ConversionRefused
from app.conversion.runners import (
    ChildLog,
    ConversionCrashed,
    ConversionDied,
    ConversionFailed,
    convert_in_child,
    log_crash,
)
from tests.conversion import standins

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures"


async def test_the_child_s_conversion_comes_back() -> None:
    conversion = await convert_in_child(
        FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.reading
    )

    assert conversion.blocks[0].text == "stand-in read up to 9 pages"
    assert conversion.printed_pages == ("5",)


async def test_the_real_conversion_runs_in_the_child() -> None:
    conversion = await convert_in_child(FIXTURES / "prose.pdf", engine="pdfplumber", max_pages=10)

    assert conversion.engine == "pdfplumber" and conversion.blocks[0].bold


async def test_a_refusal_comes_back_with_its_code() -> None:
    with pytest.raises(ConversionRefused) as refused:
        await convert_in_child(
            FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.refusing
        )

    assert refused.value.code == "needs_ocr"


async def test_a_crash_in_the_child_comes_back_by_its_kind_and_says_nothing_of_the_file(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "geheim.pdf"
    secret.write_bytes(b"%PDF-1.7")

    with pytest.raises(ConversionCrashed) as crashed:
        await convert_in_child(secret, engine="stand-in", max_pages=9, convert=standins.crashing)

    assert "RuntimeError" in str(crashed.value)
    assert "geheim" not in str(crashed.value)


async def test_a_conversion_the_child_cannot_write_down_is_a_crash() -> None:
    with pytest.raises(ConversionCrashed, match="AttributeError"):
        await convert_in_child(
            FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.answering_nothing
        )


async def test_a_child_that_exits_without_an_answer_failed_and_may_be_tried_again() -> None:
    # not the file's doing that one could tell: a library's exit, a full disk for the answer
    with pytest.raises(ConversionFailed, match="exit code 3"):
        await convert_in_child(
            FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.exiting
        )


def test_a_crash_is_logged_by_its_kind_and_frames_without_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = Path("geheim.pdf")  # a line of no frame: the frames show the lines they ran
    try:
        standins.crashing(secret, "stand-in", 9)
    except RuntimeError as error:
        with caplog.at_level(logging.ERROR):
            log_crash(error)

    assert "RuntimeError" in caplog.text and "standins.py" in caplog.text
    assert "geheim" not in caplog.text


async def test_the_child_logs_as_the_service_does_under_the_job_s_request() -> None:
    conversion = await convert_in_child(
        FIXTURES / "prose.pdf",
        engine="stand-in",
        max_pages=9,
        convert=standins.telling_its_logging,
        log=ChildLog(level="INFO", format="json", request_id="job-trace-1"),
    )

    assert conversion.blocks[0].text == "INFO JsonFormatter job-trace-1"


@pytest.mark.skipif(sys.platform == "win32", reason="a signal ends a process on POSIX")
async def test_a_child_the_kernel_kills_died() -> None:
    with pytest.raises(ConversionDied, match="signal"):
        await convert_in_child(
            FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.vanishing
        )


async def beats(beat: Path) -> int:
    return int(beat.read_text(encoding="ascii")) if beat.exists() else 0


async def started(beat: Path) -> None:
    for _ in range(200):
        if await beats(beat):
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the child never beat")


async def test_a_cancel_ends_the_child(tmp_path: Path) -> None:
    # the worker cancels the job's task when it is cancelled, or its lease is lost
    source = tmp_path / "lehrplan.pdf"
    source.write_bytes(b"%PDF-1.7")
    task = asyncio.create_task(
        convert_in_child(source, engine="stand-in", max_pages=9, convert=standins.working)
    )
    await started(source.with_suffix(".beat"))

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stopped = await beats(source.with_suffix(".beat"))
    await asyncio.sleep(0.5)

    assert await beats(source.with_suffix(".beat")) == stopped


async def test_a_deadline_ends_the_child(tmp_path: Path) -> None:
    source = tmp_path / "lehrplan.pdf"
    source.write_bytes(b"%PDF-1.7")
    deadlines: list[asyncio.Timeout] = []

    async def converting() -> None:
        async with asyncio.timeout(None) as deadline:
            deadlines.append(deadline)
            await convert_in_child(source, engine="stand-in", max_pages=9, convert=standins.working)

    task = asyncio.create_task(converting())
    # the deadline falls once the child works, however slow its start
    await started(source.with_suffix(".beat"))
    deadlines[0].reschedule(asyncio.get_running_loop().time() + 0.2)
    with pytest.raises(TimeoutError):
        await task
    stopped = await beats(source.with_suffix(".beat"))
    await asyncio.sleep(0.5)

    assert await beats(source.with_suffix(".beat")) == stopped


async def test_the_child_s_answer_leaves_no_folder_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    await convert_in_child(FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.reading)

    assert list(tmp_path.iterdir()) == []


async def test_a_cancel_at_once_leaves_no_folder_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    task = asyncio.create_task(
        convert_in_child(FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.working)
    )
    await asyncio.sleep(0)  # the call runs to its first wait

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.3)  # a folder made in a thread would show by now

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "linux", reason="process groups and OOM scores of Linux")
async def test_the_child_leads_a_group_of_its_own_the_kernel_ends_first() -> None:
    conversion = await convert_in_child(
        FIXTURES / "prose.pdf", engine="stand-in", max_pages=9, convert=standins.inspecting
    )

    group, pid, score = (part.split("=")[1] for part in conversion.blocks[0].text.split())
    assert group == pid and score == "1000"


@pytest.mark.skipif(sys.platform != "linux", reason="a process group is ended as one on POSIX")
async def test_a_cancel_ends_what_the_child_started_too(tmp_path: Path) -> None:
    source = tmp_path / "lehrplan.pdf"
    source.write_bytes(b"%PDF-1.7")
    task = asyncio.create_task(
        convert_in_child(source, engine="stand-in", max_pages=9, convert=standins.spawning)
    )
    await started(source.with_suffix(".beat"))

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stopped = await beats(source.with_suffix(".beat"))
    await asyncio.sleep(0.5)

    assert await beats(source.with_suffix(".beat")) == stopped
