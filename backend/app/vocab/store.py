"""Writing a read vocabulary into the vocabulary tables, as one release.

A load runs in one transaction under an advisory lock, so two loads at once do not interleave
and a failed one leaves the previous release whole. The same files as the latest release add
nothing. Otherwise every scheme and concept of the files is written (and revived if retired),
and those the files no longer hold are retired by the new release; so are the lexicon's
terminology profiles and cues, in the same release.
"""

from dataclasses import dataclass

import psycopg
from psycopg.types.json import Jsonb

from app.db.pool import CONNECTION_OPTIONS
from app.vocab.lexicon import KINDS, ROLES, SECTORS
from app.vocab.loader import Vocabulary

LOCK_KEY = 0x6B6B_612D_766F_6361  # "kka-voca"


@dataclass(frozen=True)
class LoadResult:
    release_id: int
    changed: bool


def load_vocabulary(conninfo: str, vocabulary: Vocabulary) -> LoadResult:
    with psycopg.connect(conninfo, **CONNECTION_OPTIONS) as connection, connection.transaction():
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
        _write_profiles(connection, vocabulary, release_id)
        _write_cues(connection, vocabulary, release_id)
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
    # Every active concept is retired first and the upsert revives those the files hold: the
    # unique index on (scheme, notation) is checked row by row, so a notation passing between
    # two concepts that both stay (a swap) would otherwise meet its old holder still active
    connection.execute("UPDATE vocab_concept SET retired_in = %s WHERE retired_in IS NULL", (release_id,))
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


def _write_profiles(connection: psycopg.Connection, vocabulary: Vocabulary, release_id: int) -> None:
    # Every active profile is retired first and the upsert revives those the files hold, as for
    # the concepts: one active profile for each sector is checked row by row, so a profile
    # renamed, or two profiles swapping their sectors, would meet the old holder still active
    connection.execute(
        "UPDATE terminology_profile SET retired_in = %s WHERE retired_in IS NULL", (release_id,)
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO terminology_profile (iri, namespace, sector_scheme, sector_iri, labels, retired_in)
            VALUES (%s, %s, %s, %s, %s, NULL)
            ON CONFLICT (iri) DO UPDATE SET namespace = EXCLUDED.namespace,
                sector_iri = EXCLUDED.sector_iri, labels = EXCLUDED.labels, retired_in = NULL
            """,
            [
                (profile.iri, profile.namespace, SECTORS, profile.sector, Jsonb(profile.labels))
                for profile in vocabulary.profiles.values()
            ],
        )


_CUE_COLUMNS = (
    "iri, profile_iri, surface_form, pattern, layout_signal, role_scheme, role_iri, kind_scheme, kind_iri,"
    " maps_to, also_maps_to, occurs_in, scope_regions, scope_document_types, scope_institution_types,"
    " scope_subjects, scope_issuers, plan_generations, valid_from, valid_until, strength, verified,"
    " recognition_hints, negative_hints, positive_examples, negative_examples, properties"
)
_CUE_UPDATES = ", ".join(
    f"{column} = EXCLUDED.{column}" for column in _CUE_COLUMNS.replace(" ", "").split(",")[1:]
)


def _write_cues(connection: psycopg.Connection, vocabulary: Vocabulary, release_id: int) -> None:
    connection.execute("UPDATE lexical_cue SET retired_in = %s WHERE retired_in IS NULL", (release_id,))
    marks = ", ".join(["%s"] * len(_CUE_COLUMNS.split(",")))
    with connection.cursor() as cursor:
        cursor.executemany(
            f"INSERT INTO lexical_cue ({_CUE_COLUMNS}, retired_in) VALUES ({marks}, NULL)"  # noqa: S608 - our names
            f" ON CONFLICT (iri) DO UPDATE SET {_CUE_UPDATES}, retired_in = NULL",
            [
                (
                    cue.iri,
                    cue.profile,
                    cue.surface_form,
                    cue.pattern,
                    cue.layout_signal,
                    ROLES,
                    cue.role,
                    KINDS,
                    cue.kind,
                    cue.maps_to,
                    cue.also_maps_to,
                    cue.occurs_in,
                    cue.scope_regions,
                    cue.scope_document_types,
                    cue.scope_institution_types,
                    cue.scope_subjects,
                    cue.scope_issuers,
                    cue.plan_generations,
                    cue.valid_from,
                    cue.valid_until,
                    cue.strength,
                    cue.verified,
                    Jsonb(cue.recognition_hints),
                    Jsonb(cue.negative_hints),
                    cue.positive_examples,
                    cue.negative_examples,
                    Jsonb(cue.properties),
                )
                for cue in vocabulary.cues.values()
            ],
        )
