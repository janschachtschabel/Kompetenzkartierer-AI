"""The job that extracts a document (plan M1 6.6, 7a), as its starter names it: its kind, and its
unique key - one extraction of a document waits or runs at a time (job.unique_key, migration
0018). Apart from app/pipeline/run.py, so the API starts it without importing the pipeline."""

from uuid import UUID

KIND = "extract.run"


def unique_key(document_id: UUID) -> str:
    """The key of the document's extraction job."""
    return f"{KIND}:{document_id}"
