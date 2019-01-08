"""Web-server constructors."""

import asyncio
from functools import partial
import sys

from aiohttp import web

from .config import RUNTIME_CONTEXT
from .event_routing import route_http_events
from .github import GitHubApp


def get_http_handler(runtime_config, github_app):
    """Return an HTTP handler with pre-filled args."""
    return partial(
        route_http_events, config=runtime_config,
        github_app=github_app,
    )


async def start_tcp_site(server_config, aiohttp_server_runner):
    """Return initialized and listening TCP site."""
    host, port = server_config.host, server_config.port
    aiohttp_tcp_site = web.TCPSite(aiohttp_server_runner, host, port)
    await aiohttp_tcp_site.start()
    print(
        f' Serving on http://{host}:{port}/ '.center(50, '='),
        file=sys.stderr,
    )
    return aiohttp_tcp_site


async def get_server_runner(http_handler):
    """Initialize server runner."""
    aiohttp_server = web.Server(http_handler)
    aiohttp_server_runner = web.ServerRunner(aiohttp_server)
    await aiohttp_server_runner.setup()
    return aiohttp_server_runner


async def run_server_forever(config):
    """Spawn an HTTP server in asyncio context."""
    async with GitHubApp(config.github) as github_app:
        print(
            # pylint: disable=protected-access
            'Starting the following GitHub App:\n'
            f'* app id: {github_app._config.app_id}\n'
            f'* user agent: {github_app._config.user_agent}\n'
            'It is installed into:',
            file=sys.stderr,
        )  # pylint: disable=protected-access
        for install_id, install_val in github_app._installations.items():
            print(
                f'* Installation id {install_id} '
                f'(expires at {install_val["access"].expires_at!s}, '
                f'installed to install_val["data"]["account"]["login"])',
                file=sys.stderr,
            )
        RUNTIME_CONTEXT.github_app = (  # pylint: disable=assigning-non-slot
            github_app
        )
        http_handler = get_http_handler(config.runtime, github_app)
        aiohttp_server_runner = await get_server_runner(http_handler)
        aiohttp_tcp_site = await start_tcp_site(
            config.server, aiohttp_server_runner,
        )
        try:
            await asyncio.get_event_loop().create_future()  # block
        except asyncio.CancelledError:
            print(file=sys.stderr)
            print(' Stopping the server '.center(50, '='), file=sys.stderr)
            await aiohttp_tcp_site.stop()
