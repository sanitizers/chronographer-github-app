"""GitHub events dispatching logic."""

import asyncio
from http import HTTPStatus
import sys

from aiohttp import web
from gidgethub import BadRequest, ValidationFailure

from .config import WEBHOOK_CONTEXT
from .event_handlers import router


async def route_http_events(request, *, config, github_app):
    """Dispatch incoming webhook events to corresponsing handlers."""
    if config.debug:
        print(f'Running a GitHub App under env={config.env}', file=sys.stderr)

    if request.method != 'POST':
        raise web.HTTPMethodNotAllowed(
            method=request.method,
            allowed_methods=('POST'),
        ) from BadRequest(HTTPStatus.METHOD_NOT_ALLOWED)

    try:
        event = await github_app.event_from_request(request)
    except ValidationFailure as no_signature_exc:
        print(
            'Got an invalid event with GitHub-Delivery-Id='
            f'{event.delivery_id}',
            file=sys.stderr,
        )
        raise web.HTTPForbidden from no_signature_exc
    else:
        print(
            'Got a valid event with GitHub-Delivery-Id='
            f'{event.delivery_id}',
            file=sys.stderr,
        )

    app_installation = await github_app.get_installation(event)
    WEBHOOK_CONTEXT.app_installation = (  # pylint: disable=assigning-non-slot
        app_installation
    )

    await asyncio.sleep(1)  # Give GitHub a sec to deal w/ eventual consistency
    await router.dispatch(event)
    return web.Response(text=f'OK: GitHub event received. It is {event!r}')
