"""Web-server constructors."""

import asyncio
from functools import partial
import logging

from aiohttp import web

from octomachinery.app.routing.webhooks_dispatcher import (
    route_github_webhook_event,
)
from octomachinery.app.runtime.context import RUNTIME_CONTEXT

from . import event_handlers  # noqa: F401; pylint: disable=unused-import
from .github import GitHubApp


logger = logging.getLogger(__name__)


def get_http_handler(runtime_config, github_app):
    """Return an HTTP handler with pre-filled args."""
    return partial(
        route_github_webhook_event, config=runtime_config,
        github_app=github_app,
    )


async def start_tcp_site(server_config, aiohttp_server_runner):
    """Return initialized and listening TCP site."""
    host, port = server_config.host, server_config.port
    aiohttp_tcp_site = web.TCPSite(aiohttp_server_runner, host, port)
    await aiohttp_tcp_site.start()
    logger.info(
        f' Serving on http://%s:%s/ '.center(50, '='),
        host, port,
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
        logger.info(
            'Starting the following GitHub App:\n'
            '* app id: %s\n'
            '* user agent: %s\n'
            'It is installed into:',
            github_app._config.app_id,  # pylint: disable=protected-access
            github_app._config.user_agent,  # pylint: disable=protected-access
        )
        # pylint: disable=protected-access
        for install_id, install_val in github_app._installations.items():
            logger.info(
                '* Installation id %s (expires at %s, installed to %s)',
                install_id,
                install_val['access'].expires_at,
                install_val['data'].account['login'],
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
            logger.info(' Stopping the server '.center(50, '='))
            await aiohttp_tcp_site.stop()
