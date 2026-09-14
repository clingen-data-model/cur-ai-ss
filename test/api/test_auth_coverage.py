"""Every route requires authentication unless it is deliberately public.

This exists because the 26 routes fixed alongside it were not forgotten all at
once -- they were each added, individually, without the dependency. Adding it to
26 more functions does not stop a 27th from being missed; asserting it here
does, and makes every exemption something a reviewer has to agree to in writing.
"""

from fastapi.routing import APIRoute

from lib.api.app import app

# Public by necessity, not by oversight:
#   login / register -- you cannot hold a token before you have an account
#   status           -- health check, polled by infrastructure with no identity
PUBLIC_ROUTES = {
    ('POST', '/auth/login'),
    ('POST', '/auth/register'),
    ('GET', '/status'),
}


def _routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods - {'HEAD', 'OPTIONS'}:
            yield method, route.path, route


def _callable_name(call) -> str:
    """Security schemes like HTTPBearer are callable instances, not functions,
    so __name__ is not always there."""
    return getattr(call, '__name__', type(call).__name__)


def _requires_auth(route: APIRoute) -> bool:
    names: set[str] = set()

    # Walk nested dependencies too: get_current_admin implies get_current_user,
    # and a route may reach either through a chain rather than directly.
    def walk(dependant) -> None:
        for sub in dependant.dependencies:
            if sub.call is not None:
                names.add(_callable_name(sub.call))
            walk(sub)

    walk(route.dependant)
    return bool(names & {'get_current_user', 'get_current_admin'})


def test_every_route_requires_auth_or_is_listed_public():
    unprotected = {
        (method, path)
        for method, path, route in _routes()
        if not _requires_auth(route) and (method, path) not in PUBLIC_ROUTES
    }

    assert not unprotected, (
        'These routes accept unauthenticated requests. Add '
        'Depends(get_current_user), or add them to PUBLIC_ROUTES with a reason:'
        f'\n  ' + '\n  '.join(f'{m} {p}' for m, p in sorted(unprotected))
    )


def test_public_routes_all_still_exist():
    """Keeps the allow-list honest: a renamed or deleted route silently stops
    being an exemption and starts being a stale entry nobody notices."""
    live = {(method, path) for method, path, _ in _routes()}

    assert PUBLIC_ROUTES <= live, PUBLIC_ROUTES - live


def test_previously_open_routes_now_reject_anonymous_requests(unauth_client):
    """The guard above proves the dependency is declared. This proves it bites.

    A sample across the shapes that were open: a plain read, a destructive
    delete, and a task enqueue that costs real API spend once the worker
    picks it up.
    """
    for method, path in [
        ('get', '/papers'),
        ('get', '/stats'),
        ('get', '/papers/collaborators'),
        ('get', '/papers/1/tasks'),
        ('delete', '/papers/1'),
        ('post', '/papers/1/tasks'),
    ]:
        response = getattr(unauth_client, method)(path)
        assert response.status_code == 401, f'{method.upper()} {path}'


def test_public_routes_stay_reachable_without_a_token(unauth_client):
    """Locking these would make the app impossible to sign in to, and would
    take the health check down with it."""
    # Wrong credentials, but reached the handler rather than being turned away.
    assert (
        unauth_client.post(
            '/auth/login', json={'email': 'nobody@example.com', 'password': 'x'}
        ).status_code
        == 401
    )

    assert unauth_client.get('/status').status_code == 200
