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


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    method = method if method in HTTP_METHODS else OTHER_METHOD
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_DURATION.labels(method, route).observe(seconds)


def render(accept: str) -> tuple[bytes, str]:
    """The process's metrics in the format the scraper's Accept header asks for, and its media type."""
    encoder, content_type = choose_encoder(accept)
    return encoder(REGISTRY), content_type
