"""Cronicler robot watching all the news being recorded as change notes!."""

import asyncio
import sys

from aiohttp import web


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
    return web.Response(text='OK')


async def run_server(loop, host, port):
    """Spawn an HTTP server in asyncio context."""
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
        pass
    loop.close()


__name__ == '__main__' and run_app()
