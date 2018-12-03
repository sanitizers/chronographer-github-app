"""Cronicler robot watching all the news being recorded as change notes!."""

import asyncio
from http import HTTPStatus
import os
import sys

from aiohttp import web
from gidgethub import BadRequest
from gidgethub.routing import Router
from gidgethub.sansio import Event


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


async def get_tcp_site(aiohttp_server_runner, host, port):
    """Spawn TCP site."""
    aiohttp_tcp_site = web.TCPSite(aiohttp_server_runner, host, int(port))
    await aiohttp_tcp_site.start()
    print(f'======= Serving on http://{host}:{port}/ ======', file=sys.stderr)
    return aiohttp_tcp_site


async def get_server_runner(aiohttp_server):
    """Initialize server runner."""
    aiohttp_server_runner = web.ServerRunner(aiohttp_server)
    await aiohttp_server_runner.setup()
    return aiohttp_server_runner


async def create_tcp_site(loop, host, port):
    """Return initialized and listening TCP site."""
    aiohttp_server = await build_server()
    aiohttp_server_runner = await get_server_runner(aiohttp_server)
    aiohttp_tcp_site = await get_tcp_site(
        aiohttp_server_runner,
        host, int(port),
    )
    return aiohttp_tcp_site


async def run_server(loop, host, port):
    """Spawn an HTTP server in asyncio context."""
    aiohttp_tcp_site = create_tcp_site(loop, host, port)
    await aiohttp_tcp_site._server.wait_closed()  # block


def run_app():
    """Start up a server using CLI args for host and port."""
    host, port = sys.argv[1:]
    loop = asyncio.get_event_loop()
    aiohttp_tcp_site = loop.run_until_complete(
        create_tcp_site(loop, host, port),
    )
    try:
        loop.run_until_complete(aiohttp_tcp_site._server.wait_closed())
    except KeyboardInterrupt:
        loop.run_until_complete(aiohttp_tcp_site.stop())
    loop.close()


__name__ == '__main__' and run_app()
