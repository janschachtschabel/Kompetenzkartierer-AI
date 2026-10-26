"""The editor's form through the API (plan M1 9.1): every account reads a sector's form - the fields of a
node and of a statement, each list with its active values and their texts; a sector without a profile
has none."""

import pytest
from fastapi.testclient import TestClient

from tests.api.test_documents import an_account, client, url

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


def test_an_account_reads_a_sector_s_form_with_its_values(client: TestClient, url: str) -> None:
    _, header = an_account(url)

    answer = client.get("/api/v1/profiles/school/form", headers=header)

    assert answer.status_code == 200, answer.text
    form = answer.json()
    assert (form["sector"], form["profile"]) == ("school", SCHOOL + "Terminology")
    node = {field["key"]: field for field in form["node"]}
    assert list(node) == ["original_title", "function", "node_type", "code", "obligation"]
    assert {key: (field["kind"], field["required"], field["many"]) for key, field in node.items()} == {
        "original_title": ("text", True, False),
        "function": ("concept", True, False),
        "node_type": ("concept", False, False),
        "code": ("text", False, False),
        "obligation": ("concept", False, False),
    }
    assert (node["original_title"]["most"], node["original_title"]["values"]) == (2000, None)
    staged = next(
        value for value in node["node_type"]["values"] if value["iri"] == SCHOOL + "Stufenabschnitt"
    )
    assert staged["label"] == "Stufenabschnitt" and staged["broader"] == [CV + "fn_grouping"]
    assert staged["examples"] and staged["definition"] and staged["delimitation"]
    assert set(staged) == {
        "iri", "notation", "label", "alt_labels", "definition", "note", "delimitation", "examples", "broader",
    }  # fmt: skip
    statement = {field["key"]: field for field in form["statement"]}
    assert statement["addressees"]["many"] and len(statement["addressees"]["values"]) == 6
    assert statement["verbatim"]["most"] == 20_000


def test_a_sector_without_a_profile_has_no_form(client: TestClient, url: str) -> None:
    _, header = an_account(url)

    answer = client.get("/api/v1/profiles/kindergarten/form", headers=header)

    assert (answer.status_code, answer.json()["code"]) == (404, "unknown_sector")
    assert client.get("/api/v1/profiles/school/form").status_code == 401
