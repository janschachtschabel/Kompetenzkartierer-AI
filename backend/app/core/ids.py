"""Ids for everything the application creates: UUIDv7 (RFC 9562).

The first 48 bits are the Unix time in milliseconds, so ids made later sort later and an index
on them grows at its end. PostgreSQL 17 has no uuidv7() and Python 3.13 no uuid.uuid7(); the
rest is random (74 bits), enough that ids made in the same millisecond do not meet.
"""

import secrets
import time
import uuid

_VERSION = 7
_VARIANT = 0b10  # RFC 4122 / 9562


def new_id() -> uuid.UUID:
    milliseconds = time.time_ns() // 1_000_000
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (milliseconds & (1 << 48) - 1) << 80 | _VERSION << 76 | random_a << 64 | _VARIANT << 62 | random_b
    return uuid.UUID(int=value)
