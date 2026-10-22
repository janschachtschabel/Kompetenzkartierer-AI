"""Prometheus metrics of the process, rendered for a scrape of /metrics on the internal port.

One process per pod keeps the values in memory; the cluster sums over the pods. Label values
come from fixed sets - route templates, known methods, status codes - never from raw input,
so the number of series stays bounded.
"""

from prometheus_client import REGISTRY, Counter, Histogram
from prometheus_client.exposition import choose_encoder

# The method is caller input: anything else (PROPFIND, invented verbs) shares one label
HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
OTHER_METHOD = "other"
# Requests are short; long work runs as a job in the worker
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)

HTTP_REQUESTS = Counter(
    "kka_http_requests_total",
    "HTTP requests by method, route template and status",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "kka_http_request_duration_seconds",
    "Duration of HTTP requests by method and route template",
    ["method", "route"],
    buckets=DURATION_BUCKETS,
)


# Jobs run from a second to an hour (a conversion with OCR, an extraction of many units)
JOB_DURATION_BUCKETS = (1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600)
# outcome, as the worker saw the run end and wrote it: done, failed (PermanentError), error
# (retried while attempts remain), cancelled, released (handed back at a shutdown), lost (its
# lease, seen at a heartbeat, by the handler or at the end - or an outcome that could not be
# written: either way the job runs again once its lease expires)
JOBS = Counter("kka_jobs_total", "Job runs by kind and how they ended", ["kind", "outcome"])
JOB_DURATION = Histogram(
    "kka_job_duration_seconds",
    "Duration of job runs by kind",
    ["kind"],
    buckets=JOB_DURATION_BUCKETS,
)


def observe_job(kind: str, outcome: str, seconds: float) -> None:
    """``kind`` is a kind the worker has a handler for: a fixed set, so the series stay few."""
    JOBS.labels(kind, outcome).inc()
    JOB_DURATION.labels(kind).observe(seconds)


def bounded_method(method: str) -> str:
    """The method as a label or a log field: one of the known ones, or ``other``."""
    return method if method in HTTP_METHODS else OTHER_METHOD


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    method = bounded_method(method)
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_DURATION.labels(method, route).observe(seconds)


def render(accept: str) -> tuple[bytes, str]:
    """The process's metrics in the format the scraper's Accept header asks for, and its media type."""
    encoder, content_type = choose_encoder(accept)
    return encoder(REGISTRY), content_type
