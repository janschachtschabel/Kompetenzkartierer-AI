"""The job kinds the worker runs, each with its handler; the pipeline stages register here (M1)."""

from app.jobs.worker import Handler

HANDLERS: dict[str, Handler] = {}
