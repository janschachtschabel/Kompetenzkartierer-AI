"""docs/uebergabe/konfiguration.md lists every setting the service reads, as the code has it.

The table between its markers is generated (``python -m app.core.config_doc``); a setting added
without regenerating it fails here, so the operators never miss one.
"""

from pathlib import Path

from app.core.config_doc import END, NONE, START, render_table, setting_rows
from app.core.settings import Settings
from app.llm.settings import LLMSettings

DOC = Path(__file__).resolve().parents[3] / "docs" / "uebergabe" / "konfiguration.md"


def test_the_document_holds_the_generated_table() -> None:
    text = DOC.read_text(encoding="utf-8")
    block = text.split(START, 1)[1].split(END, 1)[0]

    assert block.strip() == render_table().strip()


def test_every_setting_of_both_classes_has_a_row() -> None:
    names = {row.variable for row in setting_rows()}

    expected = {name.upper() for name in [*Settings.model_fields, *LLMSettings.model_fields]}
    assert names == expected


def test_a_secret_says_so_and_names_its_file_variable() -> None:
    rows = {row.variable: row for row in setting_rows()}

    assert rows["DATABASE_URL"].secret
    assert rows["OPENAI_API_KEY"].secret
    assert not rows["PUBLIC_PORT"].secret
    assert "`DATABASE_URL_FILE`" in render_table()


def test_a_default_reads_as_an_operator_would_write_it() -> None:
    rows = {row.variable: row for row in setting_rows()}

    assert rows["PUBLIC_PORT"].default == "8000"
    assert rows["STORAGE_DIR"].default == NONE
    # the repository's own path, not the machine the table was made on
    assert rows["ONTOLOGY_DIR"].default == "`ontology/` des Repositorys"
    assert rows["PUBLIC_ACCESS"].allowed == "`off` \\| `lookup` \\| `search`"
