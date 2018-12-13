"""Webhook event handlers."""
from functools import wraps
from io import StringIO
import re
import sys

from gidgethub.routing import Router
from unidiff import PatchSet

from .utils import GitHubAPIClient


_NEWS_FRAGMENT_RE = re.compile(
    r'news/[^\./]+\.(removal|feature|bugfix|doc|vendor|trivial)$',
)
"""Regexp for the valid location of news fragments."""


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
    diff_url = event.data['pull_request']['diff_url']
    async with GitHubAPIClient() as gh_api:
        diff_text = await gh_api.getitem(
            diff_url,
            oauth_token=app_installation['access'].token,
        )
        diff = PatchSet(StringIO(diff_text))
        news_fragments_added = any(
            f.is_added_file for f in diff
            if _NEWS_FRAGMENT_RE.search(f.path)
        )
        print(
            'News fragments are '
            f'{"present" if news_fragments_added else "absent"}',
            file=sys.stderr,
        )
        print(f'got pull_request event', file=sys.stderr)
        print(f'event {event.event!r}', file=sys.stderr)
        print(gh_api)
