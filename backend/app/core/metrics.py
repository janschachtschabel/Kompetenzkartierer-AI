"""Prometheus metrics of the process, rendered for a scrape of /metrics on the internal port.

One process per pod keeps the values in memory; the cluster sums over the pods. Label values
come from fixed sets - route templates, known methods, status codes - never from raw input,
so the number of series stays bounded.
"""

from collections.abc import Iterable

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
# Leases no worker renewed, handed on by a sweep (a worker died, or its loop was held): outcome
# is what became of the job - queued (attempts remain), failed (lease_lost) or cancelled
JOB_LEASES_EXPIRED = Counter(
    "kka_job_leases_expired_total", "Expired job leases by what became of the job", ["outcome"]
)


# Conversions (X0) by engine and how they ended: done, or the reason they failed
# (app/db/conversions.py FailureCode); and the pages of those done
CONVERSIONS = Counter(
    "kka_conversions_total", "Conversions by engine and how they ended", ["engine", "outcome"]
)
CONVERSION_PAGES = Counter("kka_conversion_pages_total", "Pages converted, by engine", ["engine"])


# Requests to the language model by how they ended: answered, refused (an HTTP error),
# unanswered (sent, never answered) or unsent (the provider never reached); and their tokens by
# kind - input (of it, cached_input), output, as the provider reported them, and estimated: what
# was held for one unanswered, or for an answer that reported no usage
LLM_REQUESTS = Counter(
    "kka_llm_requests_total", "Requests to the language model by how they ended", ["outcome"]
)
LLM_TOKENS = Counter("kka_llm_tokens_total", "Tokens of the language model's requests by kind", ["kind"])
# Reservations of an account's budget by what became of them: held, refused (the budget did not
# hold them), booked, late (booked already: as abandoned with its job, or by a booking asked
# again after its commit's answer was lost) or abandoned
USAGE_RESERVATIONS = Counter(
    "kka_usage_reservations_total", "Reservations of the model's budget by what became of them", ["outcome"]
)


def observe_llm_request(
    outcome: str,
    *,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_tokens: int = 0,
) -> None:
    """``outcome`` is answered, refused, unanswered or unsent: a fixed set."""
    LLM_REQUESTS.labels(outcome).inc()
    tokens = {
        "input": input_tokens,
        "cached_input": cached_input_tokens,
        "output": output_tokens,
        "estimated": estimated_tokens,
    }
    for kind, count in tokens.items():
        if count:
            LLM_TOKENS.labels(kind).inc(count)


def observe_reservations(outcome: str, count: int = 1) -> None:
    """``outcome`` is held, refused, booked, late or abandoned: a fixed set."""
    if count:
        USAGE_RESERVATIONS.labels(outcome).inc(count)


def observe_conversion(engine: str, outcome: str, pages: int = 0) -> None:
    """``engine`` is an offered one and ``outcome`` done or a FailureCode: fixed sets."""
    CONVERSIONS.labels(engine, outcome).inc()
    if pages:
        CONVERSION_PAGES.labels(engine).inc(pages)


def observe_job(kind: str, outcome: str, seconds: float) -> None:
    """``kind`` is a kind the worker has a handler for: a fixed set, so the series stay few."""
    JOBS.labels(kind, outcome).inc()
    JOB_DURATION.labels(kind).observe(seconds)


def observe_expired_leases(outcomes: Iterable[str]) -> None:
    """``outcomes`` are job statuses a sweep set: a fixed set."""
    for outcome in outcomes:
        JOB_LEASES_EXPIRED.labels(outcome).inc()


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
