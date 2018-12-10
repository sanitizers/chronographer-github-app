"""GitHub events dispatching logic."""

import asyncio
from http import HTTPStatus
import os

from aiohttp import web
from gidgethub import BadRequest, ValidationFailure
from gidgethub.sansio import Event

from .event_handlers import router


async def route_http_events(request):
    """Dispatch incoming webhook events to corresponsing handlers."""
    if request.method != 'POST':
        raise web.HTTPMethodNotAllowed(
            method=request.method,
            allowed_methods=('POST'),
        ) from BadRequest(HTTPStatus.METHOD_NOT_ALLOWED)

    secret = os.environ.get('GITHUB_WEBHOOK_SECRET')  # TODO: move to cfg layer
    try:
        event = Event.from_http(
            request.headers,
            await request.read(),
            secret=secret,
        )
    except ValidationFailure as no_signature_exc:
        raise web.HTTPForbidden from no_signature_exc

    await asyncio.sleep(1)  # Give GitHub a sec to deal w/ eventual consistency
    await router.dispatch(event)
    return web.Response(text=f'OK: GitHub event received. It is {event!r}')
