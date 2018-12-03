"""Cronicler robot watching all the news being recorded as change notes!."""

import asyncio
from http import HTTPStatus
import os
import sys

from aiohttp import web
from gidgethub import BadRequest
from gidgethub.routing import Router
from gidgethub.sansio import Event


global aiohttp_server  # Needed to kill all pending tasks correctly


async def build_server():
    """Initialize aiohttp's low-level server object with catch-all handler."""
    server = web.Server(route_http_events)
    await configure_app(server)
    return server


async def configure_app(server):
    """Assign settings to the server object."""
    pass


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
    return web.Response(text='OK: GitHub event received.')


async def run_server(loop, host, port):
    """Spawn an HTTP server in asyncio context."""
    global aiohttp_server
    aiohttp_server = await build_server()
    server = await loop.create_server(aiohttp_server, host, int(port))
    print(f'======= Serving on http://{host}:{port}/ ======', file=sys.stderr)
    await server.wait_closed()  # block


def run_app():
    """Start up a server using CLI args for host and port."""
    host, port = sys.argv[1:]
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_server(loop, host, port))
    except KeyboardInterrupt:
        loop.run_until_complete(aiohttp_server.shutdown())
    loop.close()


__name__ == '__main__' and run_app()
