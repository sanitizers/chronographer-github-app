"""Webhook event handlers."""
from datetime import datetime
from io import StringIO
import logging
import re

import attr
from check_in.github_api import DEFAULT_USER_AGENT as CHECK_IN_USER_AGENT
from check_in.github_checks_requests import (
    NewCheckRequest, UpdateCheckRequest,
    to_gh_query,
)
from unidiff import PatchSet

from octomachinery.app.routing import process_event, process_event_actions
from octomachinery.app.routing.decorators import process_webhook_payload
from octomachinery.app.runtime.context import RUNTIME_CONTEXT

from .utils import GitHubAPIClient


logger = logging.getLogger(__name__)


_NEWS_FRAGMENT_RE = re.compile(
    r'news/[^\./]+\.(removal|feature|bugfix|doc|vendor|trivial)$',
)
"""Regexp for the valid location of news fragments."""


@process_event('ping')
@process_webhook_payload
async def on_ping(*, hook, hook_id, zen):
    """React to ping webhook event."""
    app_id = hook['app_id']

    logger.info(
        'Processing ping for App ID %s '
        'with Hook ID %s '
        'sharing Zen: %s',
        app_id,
        hook_id,
        zen,
    )

    logger.info(
        'Github App Wrapper from context in ping handler: %s',
        RUNTIME_CONTEXT.github_app,
    )


@process_event('integration_installation', action='created')
@process_event('installation', action='created')  # deprecated alias
@process_webhook_payload
async def on_install(
        action,  # pylint: disable=unused-argument
        installation,
        sender,  # pylint: disable=unused-argument
        repositories=None,  # pylint: disable=unused-argument
):
    """React to GitHub App integration installation webhook event."""
    logger.info(
        'installed event install id %s',
        installation['id'],
    )
    logger.info(
        'installation=%s',
        RUNTIME_CONTEXT.app_installation,
    )


@process_event_actions(
    'pull_request',
    {
        'labeled', 'unlabeled',
        'opened', 'reopened',
        'synchronize',
    },
)
@process_event_actions('check_run', {'rerequested'})
@process_event_actions('check_suite', {'rerequested'})
async def on_pr(event):
    """React to GitHub App pull request webhook event."""
    app_installation = RUNTIME_CONTEXT.app_installation
    repo_slug = event.data['repository']['full_name']
    check_runs_base_uri = f'/repos/{repo_slug}/check-runs'
    if event.event == 'pull_request':
        pull_request = event.data['pull_request']
    elif event.event == 'check_run':
        pull_request = (
            event.data['check_run']['check_suite']['pull_requests'][0]
        )
    elif event.event == 'check_suite':
        pull_request = (
            event.data['check_suite']['pull_requests'][0]
        )
    diff_url = (
        f'https://github.com/{repo_slug}'
        f'/pull/{pull_request["number"]:d}.diff'
    )
    head_branch = pull_request['head']['ref']
    head_sha = pull_request['head']['sha']
    async with GitHubAPIClient() as gh_api:
        gh_api.requester = (
            f'{gh_api.requester} built with {CHECK_IN_USER_AGENT}'
        )

        resp = await gh_api.post(
            check_runs_base_uri,
            accept='application/vnd.github.antiope-preview+json',
            data=to_gh_query(NewCheckRequest(
                head_branch, head_sha,
                name='Timeline protection',
                started_at=f'{datetime.utcnow().isoformat()}Z',
            )),
            oauth_token=app_installation['access'].token,
        )
        logger.info(
            'Check suite ID is %s\n'
            'Check run ID is %s',
            resp['check_suite']['id'],
            resp['id'],
        )
        check_runs_updates_uri = f'{check_runs_base_uri}/{resp["id"]:d}'

        diff_text = await gh_api.getitem(
            diff_url,
            oauth_token=app_installation['access'].token,
        )
        diff = PatchSet(StringIO(diff_text))

        update_check_req = UpdateCheckRequest(
            name='Timeline protection',
            status='in_progress',
        )
        resp = await gh_api.patch(
            check_runs_updates_uri,
            accept='application/vnd.github.antiope-preview+json',
            data=to_gh_query(update_check_req),
            oauth_token=app_installation['access'].token,
        )

        news_fragments_added = [
            f for f in diff
            if f.is_added_file and _NEWS_FRAGMENT_RE.search(f.path)
        ]
        logger.info(
            'News fragments are %s',
            'present' if news_fragments_added
            else 'absent',
        )

        update_check_req = attr.evolve(
            update_check_req,
            status='completed',
            conclusion=(
                'success' if news_fragments_added
                else 'failure'
            ),
            completed_at=f'{datetime.utcnow().isoformat()}Z',
            output={
                'title': f'{update_check_req.name}: Good to go',
                'text':
                    'The following news fragments found: '
                    f'{news_fragments_added!r}',
                'summary':
                    'Great! This change has been recorded to the chronicles'
                    '\n\n'
                    '![You are good at keeping records!]('
                    'https://theeventchronicle.com'
                    '/wp-content/uploads/2014/10/vatican-library.jpg)',
            } if news_fragments_added else {
                'title': f'{update_check_req.name}: History fragments missing',
                'text': f'No files matching {_NEWS_FRAGMENT_RE} pattern added',
                'summary':
                    'Oops... This change does not have a record in the '
                    'archives. Just as if it never happened!'
                    '\n\n'
                    '![Keeping chronicles is important]('
                    'https://theeventchronicle.com'
                    '/wp-content/uploads/2014/10/vatlib7.jpg)',
            },
        )
        resp = await gh_api.patch(
            check_runs_updates_uri,
            accept='application/vnd.github.antiope-preview+json',
            data=to_gh_query(update_check_req),
            oauth_token=app_installation['access'].token,
        )

        logger.info('got %s event', event.event)
        logger.info('gh_api=%s', gh_api)
