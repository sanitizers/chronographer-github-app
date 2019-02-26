"""Cronicler robot runner."""

from octomachinery.app.server.runner import run as run_app

from . import event_handlers  # noqa: F401; pylint: disable=unused-import


__name__ == '__main__' and run_app()  # pylint: disable=expression-not-assigned
