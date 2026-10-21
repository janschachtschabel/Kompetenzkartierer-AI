"""The path of a request as the router will match it, for middlewares that run before the router."""

from starlette.types import Scope


def route_path(scope: Scope) -> str:
    """``path`` without the root path that uvicorn puts in front of it.

    Only before a slash, as Starlette's router strips it: under ``/kka`` the path ``/kkahealth``
    stays whole. The root path alone is ``/``; neither is an internal path.
    """
    path: str = scope["path"]
    root: str = scope.get("root_path", "")
    if not root or not path.startswith(root):
        return path
    rest = path[len(root) :]
    if not rest:
        return "/"
    return rest if rest.startswith("/") else path
