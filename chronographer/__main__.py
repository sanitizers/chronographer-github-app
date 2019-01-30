"""Cronicler robot runner."""

import asyncio
import sys

import attr

from .config import get_config, load_dotenv, RUNTIME_CONTEXT
from .server_machinery import run_server_forever


def run_app():
    """Start up a server using CLI args for host and port."""
    load_dotenv()
    config = get_config()
    if len(sys.argv) > 2:
        config = attr.evolve(
            config,
            server=config.WebServerConfig(*sys.argv[1:3]),
        )
    RUNTIME_CONTEXT.config = config  # pylint: disable=assigning-non-slot
    if config.runtime.debug:  # pylint: disable=no-member
        from octomachinery.github.config.utils import APP_VERSION
        print(f' App version: {APP_VERSION} '.center(50, '='), file=sys.stderr)

    try:
        asyncio.run(run_server_forever(config))
    except KeyboardInterrupt:
        print(' Exiting the app '.center(50, '='), file=sys.stderr)


__name__ == '__main__' and run_app()  # pylint: disable=expression-not-assigned
