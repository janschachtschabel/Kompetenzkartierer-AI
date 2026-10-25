"""The jobs that extract a document (plan M1 6.6, 7a) and repair it (8b), as their starter names
them: their kinds, and their unique key - one of them waits or runs on a document at a time
(job.unique_key, migration 0018), so a repair never meets an extraction. Apart from the pipeline
(app/pipeline/run.py, x6_repair.py), so the API starts them without importing it."""

from typing import Any
from uuid import UUID

KIND = "extract.run"
REPAIR_KIND = "extract.repair"


def unique_key(document_id: UUID) -> str:
    """The key of the document's extraction job, an extraction's or a repair's."""
    return f"{KIND}:{document_id}"


def document_in(payload: dict[str, Any]) -> UUID | None:
    """The document a job's payload names (``{"document_id": …}``); none for none or no id."""
    try:
        return UUID(str(payload["document_id"]))
    except (KeyError, ValueError):
        return None
