"""The register's tables (migration sources): what the code says a source may be, the database
holds it to; one file shared by its SHA-256, a source an entity of its own kind."""

import asyncio
import os
import re
import uuid
from collections.abc import Callable, Iterator
from typing import Any, get_args

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.db.migrate import migrate
from app.db.sources import StoredFile, file_row
from app.sources.register import EDUCATION_SECTORS, Provenance, RegisterStatus, RightsStatus, SourceType

pytestmark = pytest.mark.pg

SECTOR = "https://w3id.org/wlo/curriculum/vocab#sec_school"


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        # the vocabulary as app.vocab.load leaves it, cut to the one scheme the register uses
        opened.execute(
            "INSERT INTO vocab_scheme (iri, types, pref_labels, properties) VALUES (%s, '{}', '{}', '{}')",
            (EDUCATION_SECTORS,),
        )
        opened.execute(
            "INSERT INTO vocab_concept (iri, scheme_iri, types, pref_labels, alt_labels, definitions,"
            " broader, properties) VALUES (%s, %s, '{}', '{}', '{}', '{}', '{}', '{}')",
            (SECTOR, EDUCATION_SECTORS),
        )
        yield opened


def add_source(connection: psycopg.Connection, **columns: Any) -> uuid.UUID:
    source_id = new_id()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
    values = {"provenance": "upload", **columns}
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO source (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the test's own names
        (source_id, *values.values()),
    )
    return source_id


def add_file(
    connection: psycopg.Connection, digest: bytes = b"\x01" * 32, key: str | None = None
) -> uuid.UUID:
    file_id = new_id()
    connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 4, %s)",
        (file_id, digest, key or f"sources/{digest.hex()}.pdf"),
    )
    return file_id


def another_file(connection: psycopg.Connection) -> uuid.UUID:
    """A file of bytes no other file of the test holds."""
    return add_file(connection, digest=new_id().bytes * 2)


def filed(file_id: uuid.UUID, name: str = "a.pdf", status: str = "acquired") -> dict[str, Any]:
    """The columns of a source that holds the file: its name and type beside it."""
    return {"file_id": file_id, "file_name": name, "mime": "application/pdf", "register_status": status}


# The columns whose CHECK lists the values of a Literal in app/sources/register.py
LISTS: list[tuple[str, Any]] = [
    ("provenance", Provenance),
    ("rights_status", RightsStatus),
    ("source_type", SourceType),
    ("register_status", RegisterStatus),
]


def listed_values(connection: psycopg.Connection, column: str) -> set[str]:
    """The values the CHECK of a column of ``source`` lists, as the database reads it back."""
    found = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'source'::regclass"
        " AND conname = %s",
        (f"source_{column}_check",),
    ).fetchone()
    assert found is not None, f"no CHECK on source.{column}"
    return set(re.findall(r"'([^']*)'::text", found[0]))


@pytest.mark.parametrize(("column", "known"), LISTS, ids=[column for column, _ in LISTS])
def test_the_database_lists_exactly_the_values_the_code_knows(
    connection: psycopg.Connection, column: str, known: Any
) -> None:
    # both ways: a value the code knows that the database refuses, or one only the database takes
    assert listed_values(connection, column) == set(get_args(known))


@pytest.mark.parametrize(("column", "known"), LISTS, ids=[column for column, _ in LISTS])
def test_every_value_the_code_knows_is_held_and_no_other(
    connection: psycopg.Connection, column: str, known: Any
) -> None:
    for value in get_args(known):
        held = {column: value, "rights_evidence": "Amtsblatt 2023"}
        if value == "acquired":
            held |= filed(another_file(connection))
        add_source(connection, **held)

    with pytest.raises(errors.CheckViolation):
        add_source(connection, **{column: "invented"})


def test_a_new_source_s_rights_are_unclear_and_it_is_unchecked(connection: psycopg.Connection) -> None:
    source_id = add_source(connection)

    query = "SELECT rights_status, register_status FROM source WHERE id = %s"
    row = connection.execute(query, (source_id,)).fetchone()

    assert row == ("unklar", "unchecked")


def test_one_file_is_held_once_and_shared_by_its_sources(connection: psycopg.Connection) -> None:
    # the same PDF uploaded by two accounts: one file, two register entries
    file_id = add_file(connection)
    first = add_source(connection, **filed(file_id, "a.pdf"))
    second = add_source(connection, **filed(file_id, "b.pdf"))

    with pytest.raises(errors.UniqueViolation):  # the same bytes under another key
        add_file(connection, key="sources/elsewhere.pdf")
    sharing = connection.execute("SELECT count(*) FROM source WHERE file_id = %s", (file_id,)).fetchone()
    assert first != second and sharing == (2,)


async def file_at_the_gate(
    connection: psycopg.AsyncConnection, stored: StoredFile, gate: asyncio.Event
) -> uuid.UUID:
    async with connection.transaction():
        await connection.execute("SELECT 1")  # in its transaction before the gate opens
        await gate.wait()
        return await file_row(connection, stored)


@pytest.mark.anyio
async def test_the_same_bytes_filed_at_the_same_moment_are_one_file_without_an_error(
    database_url: str,
) -> None:
    # Uploads of the same bytes at once: both inserts may pass the first look for the SHA-256
    # together, and a conflict on any other unique column then fails instead of doing nothing
    # (the review's probe: 229 of 1200). Rounds, for the moment is a matter of luck.
    migrate(database_url)
    connections = [await psycopg.AsyncConnection.connect(database_url) for _ in range(4)]
    try:
        for _ in range(100):
            digest = os.urandom(32)
            stored = StoredFile(
                sha256=digest, size=4, mime="application/pdf", storage_key=f"sources/{digest.hex()}"
            )
            gate = asyncio.Event()
            filing = [asyncio.create_task(file_at_the_gate(opened, stored, gate)) for opened in connections]
            await asyncio.sleep(0.01)
            gate.set()

            outcomes = await asyncio.gather(*filing, return_exceptions=True)

            assert [repr(outcome) for outcome in outcomes if isinstance(outcome, BaseException)] == []
            assert len(set(outcomes)) == 1
    finally:
        for opened in connections:
            await opened.close()


def test_a_source_is_acquired_exactly_when_its_file_is_here(connection: psycopg.Connection) -> None:
    file_id = add_file(connection)

    with pytest.raises(errors.CheckViolation):
        add_source(connection, register_status="acquired")
    with pytest.raises(errors.CheckViolation):
        add_source(connection, **filed(file_id, status="reachable"))


@pytest.mark.parametrize("evidence", [None, "", "   "], ids=["none", "empty", "blank"])
def test_a_rights_status_other_than_unclear_holds_its_evidence(
    connection: psycopg.Connection, evidence: str | None
) -> None:
    add_source(connection, rights_status="unklar", rights_evidence=evidence)

    with pytest.raises(errors.CheckViolation):
        add_source(connection, rights_status="amtlich", rights_evidence=evidence)


def test_a_source_s_id_is_an_entity_of_kind_source(connection: psycopg.Connection) -> None:
    node_id = new_id()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'node')", (node_id,))

    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute("INSERT INTO source (id, provenance) VALUES (%s, 'upload')", (node_id,))


def test_the_sector_is_a_concept_of_the_sector_scheme(connection: psycopg.Connection) -> None:
    add_source(connection, sector_scheme=EDUCATION_SECTORS, sector_iri=SECTOR)

    with pytest.raises(errors.ForeignKeyViolation):  # no such concept in that scheme
        add_source(connection, sector_scheme=EDUCATION_SECTORS, sector_iri=SECTOR + "-invented")
    with pytest.raises(errors.CheckViolation):  # another scheme
        other = "https://w3id.org/wlo/curriculum/vocab#Formalities"
        add_source(connection, sector_scheme=other, sector_iri=SECTOR)


def test_an_address_as_long_as_the_register_takes_is_held_in_any_script(
    connection: psycopg.Connection,
) -> None:
    # 2000 signs of CJK are 6000 bytes, past what one B-tree entry holds (2704): an index on the
    # address made the longest one a 500. Signs that do not repeat, which compress no better
    # than a real address would
    url = "https://example.org/" + "".join(chr(0x4E00 + index * 7919 % 0x5200) for index in range(1980))

    add_source(connection, url=url)


@pytest.mark.parametrize("country", ["DE", "DE-BY", "AT", "CH-ZH"])
def test_a_country_is_an_iso_code(connection: psycopg.Connection, country: str) -> None:
    add_source(connection, country=country)


@pytest.mark.parametrize("country", ["Bayern", "de-by", "DE-", "DEU"])
def test_anything_else_is_no_country(connection: psycopg.Connection, country: str) -> None:
    with pytest.raises(errors.CheckViolation):
        add_source(connection, country=country)


def test_an_acquisition_names_the_source_and_the_file_it_brought(connection: psycopg.Connection) -> None:
    file_id = add_file(connection)
    source_id = add_source(connection, **filed(file_id))

    connection.execute(
        "INSERT INTO acquisition (id, source_id, file_id, method, chain) VALUES (%s, %s, %s, 'url', %s)",
        (
            new_id(),
            source_id,
            file_id,
            Jsonb(["https://example.org/a", "https://example.org/a.pdf"]),
        ),
    )
    with pytest.raises(errors.CheckViolation):
        connection.execute(
            "INSERT INTO acquisition (id, source_id, file_id, method) VALUES (%s, %s, %s, 'mail')",
            (new_id(), source_id, file_id),
        )


# --- each other CHECK of the register, by a row that breaks it and nothing else


def a_file(**columns: Any) -> Callable[[psycopg.Connection], object]:
    def write(connection: psycopg.Connection) -> object:
        values = {"id": new_id(), "sha256": b"\x02" * 32, "size_bytes": 4, "storage_key": "sources/02"}
        values |= columns
        names, marks = ", ".join(values), ", ".join(["%s"] * len(values))
        return connection.execute(
            f"INSERT INTO source_file ({names}) VALUES ({marks})",  # noqa: S608 - the test's own names
            tuple(values.values()),
        )

    return write


def a_source(**columns: Any) -> Callable[[psycopg.Connection], object]:
    return lambda connection: add_source(connection, **columns)


def a_filed_source(**columns: Any) -> Callable[[psycopg.Connection], object]:
    return lambda connection: add_source(connection, **{**filed(another_file(connection)), **columns})


def an_acquisition(**columns: Any) -> Callable[[psycopg.Connection], object]:
    def write(connection: psycopg.Connection) -> object:
        file_id = another_file(connection)
        values = {"source_id": add_source(connection, **filed(file_id)), "file_id": file_id, **columns}
        names, marks = ", ".join(values), ", ".join(["%s"] * len(values))
        return connection.execute(
            f"INSERT INTO acquisition (id, method, {names}) VALUES (%s, 'upload', {marks})",  # noqa: S608
            (new_id(), *values.values()),
        )

    return write


BROKEN = {
    "file-hash-not-sha256": a_file(sha256=b"\x02" * 31),
    "file-size-negative": a_file(size_bytes=-1),
    "file-key-empty": a_file(storage_key=""),
    "file-key-too-long": a_file(storage_key="sources/" + "a" * 505),
    "source-kind": a_source(kind="node"),
    "source-title-too-long": a_source(title="x" * 501),
    "source-url-not-http": a_source(url="ftp://example.org/a.pdf"),
    "source-url-too-long": a_source(url="https://example.org/" + "a" * 1981),
    "source-sector-iri-without-scheme": a_source(sector_iri=SECTOR),
    "source-evidence-too-long": a_source(rights_evidence="x" * 2001),
    "source-license-too-long": a_source(license="x" * 201),
    "source-file-name-empty": a_filed_source(file_name=""),
    "source-file-name-too-long": a_filed_source(file_name="x" * 256),
    "source-file-without-name": a_filed_source(file_name=None),
    "source-name-without-file": a_source(file_name="a.pdf"),
    "source-mime-not-a-type": a_filed_source(mime="PDF"),
    "source-file-without-mime": a_filed_source(mime=None),
    "source-mime-without-file": a_source(mime="application/pdf"),
    "acquisition-chain-not-a-list": an_acquisition(chain=Jsonb({"url": "https://example.org/a"})),
    "acquisition-received-name-too-long": an_acquisition(received_name="x" * 256),
}


def test_a_row_of_the_register_cases_build_is_held_as_it_stands(connection: psycopg.Connection) -> None:
    # the rows the cases below break, unbroken: each case then fails on its own change alone
    a_file()(connection)
    a_source(title="x" * 500, url="https://example.org/" + "a" * 1980, rights_evidence="x" * 2000)(connection)
    a_filed_source(file_name="x" * 255)(connection)
    an_acquisition(chain=Jsonb([]), received_name="x" * 255)(connection)


@pytest.mark.parametrize("write", BROKEN.values(), ids=BROKEN.keys())
def test_a_row_that_breaks_a_check_is_refused(
    connection: psycopg.Connection, write: Callable[[psycopg.Connection], object]
) -> None:
    with pytest.raises(errors.CheckViolation):
        write(connection)
