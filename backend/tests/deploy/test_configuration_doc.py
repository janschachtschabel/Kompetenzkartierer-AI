"""docs/uebergabe/konfiguration.md lists every setting the service reads, as the code has it.

The table between its markers is generated (``python -m app.core.config_doc``); a setting added
without regenerating it fails here, so the operators never miss one.
"""

from pathlib import Path
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo

from app.core import config_doc
from app.core.config_doc import CONDITIONS, END, NONE, START, render_table, setting_rows

DOC = Path(__file__).resolve().parents[3] / "docs" / "uebergabe" / "konfiguration.md"


class Invented(BaseModel):
    """Fields of kinds the service's settings may take on later."""

    flag: bool = False
    made: str = Field(default_factory=lambda: "made")
    folder: Path = Path("/var/lib/kka")
    choice: str = "a|b"
    named: Annotated[str, Field(pattern=r"^[a-z]+$")] = "abc"
    short: Annotated[str, Field(min_length=3, max_length=8)] = "abcd"
    coded: Annotated[str, Field(pattern=r"^[a-z]+$", max_length=8)] = "abc"
    mode: Literal["a|b", "c"] = "c"
    mixed: int | str = 1


def _field(name: str) -> FieldInfo:
    return Invented.model_fields[name]


def test_the_document_holds_the_generated_table() -> None:
    text = DOC.read_text(encoding="utf-8")
    block = text.split(START, 1)[1].split(END, 1)[0]

    assert block.strip() == render_table().strip()


def test_a_secret_says_so_and_names_its_file_variable() -> None:
    rows = {row.variable: row for row in setting_rows()}

    assert rows["DATABASE_URL"].secret
    assert rows["OPENAI_API_KEY"].secret
    assert not rows["PUBLIC_PORT"].secret
    assert "`DATABASE_URL_FILE`" in render_table()


def test_a_default_reads_as_an_operator_would_write_it() -> None:
    rows = {row.variable: row for row in setting_rows()}

    assert rows["PUBLIC_PORT"].default == "8000"
    assert rows["HOST"].default == "`127.0.0.1`"
    # the repository's own path, not the machine the table was made on
    assert rows["ONTOLOGY_DIR"].default == "`ontology/` des Repositorys"
    assert rows["PUBLIC_ACCESS"].allowed == "`off` \\| `lookup` \\| `search`"


def test_a_pattern_the_code_enforces_is_shown() -> None:
    rows = {row.variable: row for row in setting_rows()}

    assert rows["S3_BUCKET"].allowed == "Text nach Muster `^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`"
    assert rows["OPENAI_BASE_URL"].allowed.startswith("Text nach Muster `^https?://")


def test_a_setting_needed_only_sometimes_says_when() -> None:
    # without a default the table said "-", and an operator took API_KEY_PEPPER for optional
    rows = {row.variable: row for row in setting_rows()}

    assert rows["API_KEY_PEPPER"].default == f"{NONE}; Pflicht für die API und `app.bootstrap`"
    assert rows["STORAGE_DIR"].default == f"{NONE}; Pflicht bei `STORAGE_BACKEND=fs`"
    assert rows["S3_BUCKET"].default == f"{NONE}; Pflicht bei `STORAGE_BACKEND=s3`"
    assert rows["S3_ACCESS_KEY"].default == f"{NONE}; nur zusammen mit `S3_SECRET_KEY`"


def test_every_condition_names_a_setting_that_exists() -> None:
    assert set(CONDITIONS) <= {row.variable for row in setting_rows()}


@pytest.mark.parametrize(
    ("name", "allowed", "default"),
    [
        ("flag", "`true` \\| `false`", "`false`"),
        ("made", "Text", "`made`"),
        ("folder", "Pfad", "`/var/lib/kka`"),  # the same on Windows and in CI
        ("choice", "Text", "`a\\|b`"),  # a bare | would split the row
        ("named", "Text nach Muster `^[a-z]+$`", "`abc`"),
        ("short", "Text, mindestens 3, höchstens 8 Zeichen", "`abcd`"),
        ("coded", "Text nach Muster `^[a-z]+$`, höchstens 8 Zeichen", "`abc`"),
        ("mode", "`a\\|b` \\| `c`", "`c`"),
    ],
)
def test_a_field_of_a_later_kind_renders_as_meant(name: str, allowed: str, default: str) -> None:
    assert config_doc._allowed(_field(name)) == allowed
    assert config_doc._default(_field(name)) == default


def test_a_type_without_a_rendering_fails_rather_than_reading_as_text() -> None:
    with pytest.raises(TypeError, match="no rendering"):
        config_doc._allowed(_field("mixed"))


def test_markers_out_of_order_leave_the_document_as_it_was(tmp_path: Path) -> None:
    document = tmp_path / "konfiguration.md"
    document.write_text(f"before\n{END}\nmiddle\n{START}\nafter\n", encoding="utf-8")
    before = document.read_bytes()

    assert config_doc.main(document) == 1
    assert document.read_bytes() == before
