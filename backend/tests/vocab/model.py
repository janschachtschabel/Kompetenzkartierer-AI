"""A small model folder for the vocabulary tests, with the three folders the reader requires."""

from pathlib import Path

PREFIXES = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix ex: <https://example.org/vocab/> .
"""


def write_model(root: Path, vocabulary: str, profiles: dict[str, str] | None = None) -> Path:
    """``vocabulary`` (Turtle with its own prefixes) as vokabulare/farben.ttl beside empty model
    files; ``profiles``: more files under profile/, by their path there ("laender/x.ttl")."""
    for folder in ("ontologie", "profile"):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / "empty.ttl").write_text(PREFIXES, encoding="utf-8")
    (root / "vokabulare").mkdir(parents=True, exist_ok=True)
    (root / "vokabulare" / "farben.ttl").write_text(vocabulary, encoding="utf-8")
    for name, content in (profiles or {}).items():
        path = root / "profile" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root
