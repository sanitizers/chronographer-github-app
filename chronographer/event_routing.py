"""GitHub events dispatching logic."""

import asyncio
from http import HTTPStatus
import os

from aiohttp import web
from gidgethub import BadRequest
from gidgethub.routing import Router
from gidgethub.sansio import Event


async def route_http_events(request):
    """Dispatch incoming webhook events to corresponsing handlers."""
    if request.method != 'POST':
        raise web.HTTPMethodNotAllowed(
            method=request.method,
            allowed_methods=('POST'),
        ) from BadRequest(HTTPStatus.METHOD_NOT_ALLOWED)
    router = Router()
    secret = os.environ.get('GITHUB_WEBHOOK_SECRET')  # TODO: move to cfg layer
    event = Event.from_http(
        request.headers,
        await request.read(),
        secret=secret,
    )
    await asyncio.sleep(1)  # Give GitHub a sec to deal w/ eventual consistency
    await router.dispatch(event)
    return web.Response(text=f'OK: GitHub event received. It is {event!r}')
