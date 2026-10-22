"""deploy/helm-values.example.yaml: what T6 can rely on when they build the chart from it."""

import ipaddress
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from app.api.internal import READY_TIMEOUT_S
from app.core.settings import Settings

VALUES: dict[str, Any] = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "deploy" / "helm-values.example.yaml").read_text(encoding="utf-8")
)


def test_the_probes_ask_the_internal_port() -> None:
    probes = VALUES["api"]["probes"]

    assert {probe["port"] for probe in probes.values()} == {9000}
    assert probes["readiness"]["path"] == "/ready"
    assert probes["liveness"]["path"] == "/health"


def test_readiness_waits_longer_than_ready_itself() -> None:
    # /ready waits for a pool connection and then for its query, each up to READY_TIMEOUT_S; a
    # probe that gives up sooner takes a slow database for a dead pod
    assert VALUES["api"]["probes"]["readiness"]["timeoutSeconds"] >= 2 * READY_TIMEOUT_S + 1


def test_no_container_runs_as_root_or_with_capabilities() -> None:
    pod = VALUES["podSecurityContext"]
    container = VALUES["containerSecurityContext"]

    assert pod["runAsNonRoot"] is True
    assert pod["runAsUser"] == 10001
    assert container["readOnlyRootFilesystem"] is True
    assert container["capabilities"]["drop"] == ["ALL"]
    assert container["allowPrivilegeEscalation"] is False


@pytest.mark.parametrize("part", ["api", "worker", "migrate", "vocab"])
def test_secrets_are_named_never_given(part: str) -> None:
    secrets = VALUES[part]["secrets"]

    assert set(secrets) == {"existingSecret", "keys"}
    assert all(isinstance(key, str) and key.isupper() for key in secrets["keys"])
    assert not {"DATABASE_URL", "API_KEY_PEPPER", "OPENAI_API_KEY"} & set(VALUES[part].get("env", {}))


def test_the_ingress_never_opens_the_internal_port() -> None:
    ingress = VALUES["ingress"]

    assert ingress["routes"]
    assert all(route["servicePort"] not in (9000, "internal") for route in ingress["routes"])


def test_a_stuck_worker_is_restarted_by_its_liveness_probe() -> None:
    # /health answers only while the worker's loop turns; the worker sits behind no Service, so
    # it has no readiness probe
    probes = VALUES["worker"]["probes"]

    assert set(probes) == {"liveness"}
    assert probes["liveness"]["port"] == 9000
    assert probes["liveness"]["path"] == "/health"


def test_the_worker_may_finish_its_job_before_kubernetes_kills_it() -> None:
    worker = VALUES["worker"]
    default = Settings.model_fields["job_shutdown_grace_s"].default
    grace = float(worker["env"].get("JOB_SHUTDOWN_GRACE_S", default))

    assert worker["terminationGracePeriodSeconds"] >= grace + 5


def test_the_database_and_the_object_store_can_be_the_operators() -> None:
    assert VALUES["postgresql"]["enabled"] is False
    assert VALUES["objectStorage"]["env"]["STORAGE_BACKEND"] == "s3"


def test_the_migration_runs_once_per_release_before_the_pods() -> None:
    migrate = VALUES["migrate"]

    assert migrate["command"] == ["python", "-m", "app.db.migrate"]
    assert "pre-upgrade" in migrate["hook"] and "pre-install" in migrate["hook"]


@pytest.mark.parametrize("part", ["migrate", "vocab"])
def test_a_one_off_job_runs_once_ends_in_time_and_makes_room_for_the_next(part: str) -> None:
    # A retried migration might run beside a stuck first one; a hook job left behind blocks the
    # next release's job of the same name
    job = VALUES[part]

    assert job["backoffLimit"] == 0
    assert job["activeDeadlineSeconds"] > 0
    assert job["hookDeletePolicy"] == "before-hook-creation"
    assert {"requests", "limits"} <= set(job["resources"])


def test_the_web_server_has_its_probes_resources_and_user() -> None:
    web = VALUES["web"]

    assert {probe["path"] for probe in web["probes"].values()} == {"/healthz"}
    assert {probe["port"] for probe in web["probes"].values()} == {8080}
    assert {"requests", "limits"} <= set(web["resources"])
    # the pod's 10001 is the API image's user; nginx-unprivileged runs as 101
    assert web["securityContext"]["runAsUser"] == 101


@pytest.mark.parametrize("part", ["api", "web"])
def test_a_drain_of_nodes_leaves_one_pod_serving(part: str) -> None:
    assert VALUES["podDisruptionBudget"][part] == {"minAvailable": 1}


PRIVATE_V4 = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"}
PRIVATE_V6 = {"fc00::/7", "fe80::/10", "fec0::/10"}


def test_the_worker_reaches_the_public_web_on_80_and_443_and_nothing_private() -> None:
    # source.fetch imports a file from an address an account names; without this entry the
    # policy blocked every import, and with 0.0.0.0/0 alone the cluster's own networks lay open
    [public] = [rule for rule in VALUES["networkPolicy"]["egress"]["worker"] if isinstance(rule, dict)]
    blocks = {block["ipBlock"]["cidr"]: block["ipBlock"]["except"] for block in public["to"]}

    assert public["name"] == "public-web"
    assert sorted(public["ports"]) == [80, 443]
    assert set(blocks) == {"0.0.0.0/0", "::/0"}
    for cidr, private in (("0.0.0.0/0", PRIVATE_V4), ("::/0", PRIVATE_V6)):
        networks = [entry for entry in blocks[cidr] if not entry.startswith("<")]
        placeholders = [entry for entry in blocks[cidr] if entry.startswith("<")]
        assert private <= set(networks)
        # an exception outside its block's family is refused by the API server
        assert {ipaddress.ip_network(entry).version for entry in networks} == {
            ipaddress.ip_network(cidr).version
        }
        assert placeholders, "the cluster's own networks go in by name of the operator"
    assert any(
        ipaddress.ip_address("169.254.169.254") in ipaddress.ip_network(entry)
        for entry in blocks["0.0.0.0/0"]
        if not entry.startswith("<")
    )
