"""Which route a request was meant for: its full template and the query names it declares.

Matched as Starlette's router matches - the first full match, else the first partial one (a
405) - against the scope as the request came in; the router changes the scope later (a mount
sets its root path). The route FastAPI leaves in the scope will not do: it names the path
within its router, without the prefix it was included under. A mounted app counts under its
mount path. The contexts are built once and again when routes were added, not per request.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi.routing import RouteContext, iter_route_contexts
from starlette.routing import BaseRoute, Match
from starlette.types import Scope

UNMATCHED_ROUTE = "unmatched"  # the raw path of a 404 is caller input


@dataclass(frozen=True)
class RouteMatch:
    template: str  # a bounded label: one of the application's templates or "unmatched"
    query_names: frozenset[str]  # the query parameters the route declares, its dependencies' too


UNMATCHED = RouteMatch(UNMATCHED_ROUTE, frozenset())


class RouteIndex:
    def __init__(self, routes: Sequence[BaseRoute]) -> None:
        self.routes = routes  # the application's live list: routes added later count
        self._entries: list[tuple[RouteContext, RouteMatch]] = []
        self._built_for = -1

    def match(self, scope: Scope) -> RouteMatch:
        partial: RouteMatch | None = None
        for context, found in self._current():
            kind, _ = context.matches(scope)
            if kind is Match.FULL:
                return found
            if kind is Match.PARTIAL and partial is None:
                partial = found
        return partial or UNMATCHED

    def _current(self) -> list[tuple[RouteContext, RouteMatch]]:
        if len(self.routes) != self._built_for:
            self._entries = [
                (context, RouteMatch(context.path or UNMATCHED_ROUTE, _query_names(context.original_route)))
                for context in iter_route_contexts(self.routes)
            ]
            self._built_for = len(self.routes)
        return self._entries


def _query_names(route: BaseRoute) -> frozenset[str]:
    dependant = getattr(route, "dependant", None)
    names: set[str] = set()
    pending = [dependant] if dependant is not None else []
    while pending:
        current = pending.pop()
        names.update(field.alias for field in current.query_params)
        pending.extend(current.dependencies)
    return frozenset(names)
