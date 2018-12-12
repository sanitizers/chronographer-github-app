"""Webhook event handlers."""
from functools import wraps
import sys

import aiohttp
import gidgethub.aiohttp
from gidgethub.routing import Router

from .utils import USER_AGENT


router = Router()  # pylint: disable=invalid-name


def listen_to_event_actions(event_name, actions):
    """Subscribe to multiple events."""
    def decorator(original_function):
        def wrapper(*args, **kwargs):
            return original_function(*args, **kwargs)
        for action in actions:
            wrapper = router.register(event_name, action=action)(wrapper)
        return wraps(original_function)(wrapper)
    return decorator


@router.register('ping')
async def on_ping(event, app_installation):
    """React to ping webhook event."""
    print(f'pinged {event!r}', file=sys.stderr)
    print(f'installation={app_installation!r}', file=sys.stderr)


@router.register('integration_installation', action='created')
@router.register('installation', action='created')  # deprecated alias
async def on_install(event, app_installation):
    """React to GitHub App integration installation webhook event."""
    print(f'installed {event!r}', file=sys.stderr)
    print(
        f'installed event dat install id {event.data["installation"]["id"]!r}',
        file=sys.stderr,
    )
    print(
        f'installed event delivery_id {event.delivery_id!r}',
        file=sys.stderr,
    )
    print(f'installation={app_installation!r}', file=sys.stderr)


@listen_to_event_actions(
    'pull_request',
    {
        'labeled', 'unlabeled',
        'opened', 'reopened',
        'synchronize',
    },
)
async def on_pr(event, app_installation):
    """React to GitHub App pull request webhook event."""
    async with aiohttp.ClientSession() as session:
        gh_api = gidgethub.aiohttp.GitHubAPI(
            session,
            USER_AGENT,
            oauth_token=app_installation['access'].token,
        )
        print(f'got pull_request event', file=sys.stderr)
        print(f'event {event.event!r}', file=sys.stderr)
        print(gh_api)
