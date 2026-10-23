"""The conversions of register files and their blocks (migration 0011; plan M1, 3.5)."""

from typing import Literal

ConversionStatus = Literal["pending", "done", "failed"]
# Why a conversion failed: a refusal of the file (app/conversion/convert.py) or what ended the job
FailureCode = Literal[
    "unreadable", "too_many_pages", "needs_ocr", "empty", "timed_out", "died", "not_pdf", "file_gone"
]
