"""Writing a read vocabulary into the vocabulary tables, as one release.

A load runs in one transaction under an advisory lock, so two loads at once do not interleave
and a failed one leaves the previous release whole. The same files as the latest release add
nothing. Otherwise every scheme and concept of the files is written (and revived if retired),
and those the files no longer hold are retired by the new release.
"""

from dataclasses import dataclass

import psycopg
from psycopg.types.json import Jsonb

from app.db.pool import CONNECT_TIMEOUT_S
from app.vocab.loader import Vocabulary

LOCK_KEY = 0x6B6B_612D_766F_6361  # "kka-voca"


@dataclass(frozen=True)
class LoadResult:
    release_id: int
    changed: bool


def load_vocabulary(conninfo: str, vocabulary: Vocabulary) -> LoadResult:
    with psycopg.connect(conninfo, connect_timeout=CONNECT_TIMEOUT_S) as connection, connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        latest = connection.execute(
            "SELECT id, content_hash FROM vocab_release ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest is not None and latest[1] == vocabulary.content_hash:
            return LoadResult(int(latest[0]), changed=False)
        row = connection.execute(
            "INSERT INTO vocab_release (content_hash, files) VALUES (%s, %s) RETURNING id",
            (vocabulary.content_hash, Jsonb(vocabulary.files)),
        ).fetchone()
        assert row is not None  # noqa: S101 - RETURNING always yields the row
        release_id = int(row[0])
        _write_schemes(connection, vocabulary, release_id)
        _write_concepts(connection, vocabulary, release_id)
    return LoadResult(release_id, changed=True)


def _write_schemes(connection: psycopg.Connection, vocabulary: Vocabulary, release_id: int) -> None:
    connection.execute(
        "UPDATE vocab_scheme SET retired_in = %s WHERE retired_in IS NULL AND NOT (iri = ANY(%s))",
        (release_id, list(vocabulary.schemes)),
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO vocab_scheme (iri, types, pref_labels, properties, retired_in)
            VALUES (%s, %s, %s, %s, NULL)
            ON CONFLICT (iri) DO UPDATE SET types = EXCLUDED.types, pref_labels = EXCLUDED.pref_labels,
                properties = EXCLUDED.properties, retired_in = NULL
            """,
            [
                (scheme.iri, scheme.types, Jsonb(scheme.pref_labels), Jsonb(scheme.properties))
                for scheme in vocabulary.schemes.values()
            ],
        )


def _write_concepts(connection: psycopg.Connection, vocabulary: Vocabulary, release_id: int) -> None:
    # Retired first: a notation may pass from a concept the files dropped to a new one
    connection.execute(
        "UPDATE vocab_concept SET retired_in = %s WHERE retired_in IS NULL AND NOT (iri = ANY(%s))",
        (release_id, list(vocabulary.concepts)),
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO vocab_concept (iri, scheme_iri, types, notation, pref_labels, alt_labels,
                definitions, broader, properties, retired_in)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (iri) DO UPDATE SET scheme_iri = EXCLUDED.scheme_iri, types = EXCLUDED.types,
                notation = EXCLUDED.notation, pref_labels = EXCLUDED.pref_labels,
                alt_labels = EXCLUDED.alt_labels, definitions = EXCLUDED.definitions,
                broader = EXCLUDED.broader, properties = EXCLUDED.properties, retired_in = NULL
            """,
            [
                (
                    concept.iri,
                    concept.scheme,
                    concept.types,
                    concept.notation,
                    Jsonb(concept.pref_labels),
                    Jsonb(concept.alt_labels),
                    Jsonb(concept.definitions),
                    concept.broader,
                    Jsonb(concept.properties),
                )
                for concept in vocabulary.concepts.values()
            ],
        )
