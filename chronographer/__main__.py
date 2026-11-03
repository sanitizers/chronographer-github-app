"""Cronicler robot runner."""

import asyncio

from octomachinery.app.server.runner import run as run_app
from octomachinery.utils.versiontools import get_version_from_scm_tag

from . import event_handlers  # noqa: F401; pylint: disable=unused-import


# NOTE: `octomachinery` caps `anyio` below v2, and `anyio` v1 boots the app
# NOTE: through `asyncio.get_event_loop()`, relying on it to implicitly make
# NOTE: a loop when the main thread has none. Python 3.14 dropped that
# NOTE: fallback and raises `RuntimeError` instead, so the app never starts
# NOTE: there. Making the loop up front is just what the interpreter used to
# NOTE: do for us: it is a no-op on older Pythons and stops being necessary
# NOTE: once `octomachinery` grows `anyio` v2+ support.
# NOTE: The GitHub Action entry point (`chronographer.action`) is unaffected —
# NOTE: `octomachinery`'s action runner goes through `asyncio.run()`.
# pylint: disable-next=expression-not-assigned
__name__ == '__main__' and asyncio.set_event_loop(asyncio.new_event_loop())

__name__ == '__main__' and run_app(  # pylint: disable=expression-not-assigned
    name='Chronographer-Bot',
    version=get_version_from_scm_tag(root='..', relative_to=__file__),
    url='https://github.com/apps/chronographer',
)
