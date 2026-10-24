"""The parts of the prefix (app/pipeline/prefix.py) that X3's and X4's requests carry beside a
document's blocks (plan M1 7b, F5, F7, F8; konzept §13.1): the document profile as the store holds
it, the sections its windows are cut by, the choice lists X3 read. Each is read from the store as
it stands when the stage starts, so every unit of the stage reads the same bytes.
"""

from uuid import UUID

import psycopg

from app.db.documents import DocumentError
from app.vocab.lookup import REGIONS, by_notation, concept_texts

_PROFILE = """
SELECT d.title, d.document_type_iri, d.sector_iri, d.regions, p.term_mappings
FROM document d LEFT JOIN document_profile p ON p.document_id = d.id
WHERE d.id = %s
"""
_SPECIFICATIONS = "SELECT key, spec_kind, title, field_text FROM specification WHERE document_id = %s"


async def profile_text(connection: psycopg.AsyncConnection, document_id: UUID) -> str:
    """The document profile as the prefix writes it: what X1 wrote of the document (the editors may
    have changed it since) - what the document does not say is left out, a value the vocabularies
    no longer hold named by its IRI. DocumentError for no document."""
    cursor = await connection.execute(_PROFILE, (document_id,))
    found = await cursor.fetchone()
    if found is None:
        raise DocumentError(f"no document {document_id}")
    title, document_type, sector, regions, terms = found
    cursor = await connection.execute(_SPECIFICATIONS, (document_id,))
    specifications = sorted(await cursor.fetchall())
    region_iris = {
        notation: entry.iri if (entry := await by_notation(connection, REGIONS, notation)) else notation
        for notation in regions
    }
    named = [document_type, sector, *region_iris.values(), *(term["mapsTo"] for term in terms or [])]
    texts = await concept_texts(connection, {iri for iri in named if iri})

    def label(iri: str) -> str:
        return texts[iri].label if iri in texts else iri

    lines = [f"Titel: {title}"] if title else []
    if document_type:
        lines.append(f"Dokumenttyp: {label(document_type)}")
    lines.append(f"Bildungsbereich: {label(sector)}")
    if region_iris:
        lines.append("Regionen: " + ", ".join(sorted(label(iri) for iri in region_iris.values())))
    if specifications:
        lines.append("Spezifikationen:")
        lines.extend(
            f"- {key} ({kind}): {named_as}" + (f"; Fach/Feld: {field}" if field else "")
            for key, kind, named_as, field in specifications
        )
    # each once: X1 may name a term at each block it found it in
    own = dict.fromkeys(f"- „{term['documentTerm']}“ → {label(term['mapsTo'])}" for term in terms or [])
    if own:
        lines.append("Eigene Bezeichnungen des Dokuments:")
        lines.extend(own)
    return "\n".join(lines)
