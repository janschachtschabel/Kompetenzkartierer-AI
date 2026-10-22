"""Ids are UUIDv7 (RFC 9562): time-ordered, so an index on them stays compact."""

import time
import uuid

from app.core.ids import new_id


def test_an_id_is_a_version_7_uuid_of_the_rfc_variant() -> None:
    value = new_id()

    assert isinstance(value, uuid.UUID)
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_an_id_carries_the_current_time_in_milliseconds() -> None:
    before = time.time_ns() // 1_000_000
    value = new_id()
    after = time.time_ns() // 1_000_000

    assert before <= value.int >> 80 <= after


def test_ids_made_later_sort_later() -> None:
    first = new_id()
    time.sleep(0.002)
    second = new_id()

    assert first < second


def test_ids_made_at_once_differ() -> None:
    assert len({new_id() for _ in range(10_000)}) == 10_000
