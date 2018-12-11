"""Cronicler robot runner."""

import asyncio
import sys

from .config import load_dotenv
from .server_machinery import run_server_forever


def run_app():
    """Start up a server using CLI args for host and port."""
    load_dotenv()

    host, port = sys.argv[1:]
    port = int(port)
    try:
        asyncio.run(run_server_forever(host, port))
    except KeyboardInterrupt:
        print(' Exiting the app '.center(50, '='), file=sys.stderr)


__name__ == '__main__' and run_app()
