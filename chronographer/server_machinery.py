"""Web-server constructors."""

import asyncio
import sys

from aiohttp import web

from .event_routing import route_http_events


async def build_server():
    """Initialize aiohttp's low-level server object with catch-all handler."""
    server = web.Server(route_http_events)
    await configure_app(server)
    return server


async def configure_app(server):
    """Assign settings to the server object."""


async def get_tcp_site(aiohttp_server_runner, host, port):
    """Spawn TCP site."""
    aiohttp_tcp_site = web.TCPSite(aiohttp_server_runner, host, port)
    await aiohttp_tcp_site.start()
    print(
        f' Serving on http://{host}:{port}/ '.center(50, '='),
        file=sys.stderr,
    )
    return aiohttp_tcp_site


async def get_server_runner(aiohttp_server):
    """Initialize server runner."""
    aiohttp_server_runner = web.ServerRunner(aiohttp_server)
    await aiohttp_server_runner.setup()
    return aiohttp_server_runner


async def create_tcp_site(host, port):
    """Return initialized and listening TCP site."""
    aiohttp_server = await build_server()
    aiohttp_server_runner = await get_server_runner(aiohttp_server)
    aiohttp_tcp_site = await get_tcp_site(
        aiohttp_server_runner,
        host, port,
    )
    return aiohttp_tcp_site


async def run_server_forever(host, port):
    """Spawn an HTTP server in asyncio context."""
    aiohttp_tcp_site = await create_tcp_site(host, port)
    try:
        await asyncio.get_event_loop().create_future()  # block
    except asyncio.CancelledError:
        print(file=sys.stderr)
        print(' Stopping the server '.center(50, '='), file=sys.stderr)
        await aiohttp_tcp_site.stop()
