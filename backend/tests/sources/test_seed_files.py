"""The comparison dataset's files are the ones the README names: byte for byte, by their SHA-256.

They came from elsewhere (README: origin, licence); a file changed by hand, or by Git turning its
line endings, would seed the register with what nobody published.
"""

import hashlib
import re
from pathlib import Path

SEED = Path(__file__).resolve().parents[3] / "data" / "seed" / "vergleichsdatensatz"
# A row of the README's table of files: | `name` | bytes | sha256 |
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([\d.]+)\s*\|\s*([0-9a-f]{64})\s*\|", re.MULTILINE)


def listed() -> dict[str, tuple[int, str]]:
    readme = (SEED / "README.md").read_text(encoding="utf-8")
    return {name: (int(size.replace(".", "")), digest) for name, size, digest in ROW.findall(readme)}


def test_the_readme_lists_the_two_files() -> None:
    assert sorted(listed()) == ["lehrplan_dokumente_de.csv", "umgehungshinweise_de.csv"]


def test_every_data_file_is_listed() -> None:
    present = sorted(path.name for path in SEED.iterdir() if path.suffix == ".csv")

    assert present == sorted(listed())


def test_each_file_is_the_one_its_checksum_names() -> None:
    for name, (size, digest) in listed().items():
        data = (SEED / name).read_bytes()

        assert len(data) == size, name
        assert hashlib.sha256(data).hexdigest() == digest, name
