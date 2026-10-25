"""The job kinds the worker runs, each with its handler bound to the job context; the pipeline
stages register in ``make_handlers`` (M1)."""

from collections.abc import Collection, Mapping
from functools import partial

from app.jobs.context import JobContext
from app.jobs.worker import Handler


class UnknownJobKind(ValueError):
    """WORKER_KINDS names a kind no handler has."""


def make_handlers(context: JobContext) -> dict[str, Handler]:
    from app.conversion import job as convert_job
    from app.pipeline import run as extract_run
    from app.pipeline import x6_repair
    from app.sources import check_job, fetch_job

    return {
        fetch_job.KIND: partial(fetch_job.fetch_source, context),
        check_job.KIND: partial(check_job.check_sources, context),
        convert_job.KIND: partial(convert_job.convert_source, context),
        extract_run.KIND: partial(extract_run.extract_document, context),
        x6_repair.REPAIR_KIND: partial(x6_repair.repair_document, context),
    }


def select_handlers(handlers: Mapping[str, Handler], kinds: Collection[str]) -> dict[str, Handler]:
    """The handlers of ``kinds``, or all of them for none. A kind without a handler stops the start:
    a typo would leave a pod idle that looks busy in the deployment."""
    if not kinds:
        return dict(handlers)
    unknown = sorted(set(kinds) - set(handlers))
    if unknown:
        raise UnknownJobKind(f"WORKER_KINDS names kinds no handler has: {', '.join(unknown)}")
    return {kind: handler for kind, handler in handlers.items() if kind in kinds}
