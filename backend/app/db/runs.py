"""The runs of the pipeline's stages on a document (plan M1 6.6; table extraction_run): one for each
stage and attempt of a job, ended with its outcome and what it made."""

from typing import Literal

# As migration 0017 lists them (tests/db/test_runs_schema.py)
RunOutcome = Literal["done", "failed", "budget_exhausted"]
