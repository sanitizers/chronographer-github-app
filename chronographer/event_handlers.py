"""Webhook event handlers."""
from datetime import datetime
from io import StringIO
import logging
import re

import attr
from unidiff import PatchSet

from octomachinery.app.routing import process_event, process_event_actions
from octomachinery.app.routing.decorators import process_webhook_payload
from octomachinery.app.runtime.context import RUNTIME_CONTEXT
from octomachinery.github.models.checks_api_requests import (
    NewCheckRequest, UpdateCheckRequest,
    to_gh_query,
)

from .file_utils import get_towncrier_config


logger = logging.getLogger(__name__)


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

    gh_api = RUNTIME_CONTEXT.app_installation_client

    resp = await gh_api.post(
        check_runs_base_uri,
        preview_api_version='antiope',
        data=to_gh_query(NewCheckRequest(
            head_branch, head_sha,
            name='Timeline protection',
            status='queued',
            started_at=f'{datetime.utcnow().isoformat()}Z',
        )),
    )
    logger.info(
        'Check suite ID is %s',
        resp['check_suite']['id'],
    )
    logger.info(
        'Check run ID is %s',
        resp['id'],
    )
    check_runs_updates_uri = f'{check_runs_base_uri}/{resp["id"]:d}'

    diff_text = await gh_api.getitem(
        diff_url,
    )
    diff = PatchSet(StringIO(diff_text))

    update_check_req = UpdateCheckRequest(
        name='Timeline protection',
        status='in_progress',
    )
    resp = await gh_api.patch(
        check_runs_updates_uri,
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    _tc_fragment_re = await compile_towncrier_fragments_regex(ref=head_sha)

    news_fragments_added = [
        f for f in diff
        if f.is_added_file and _tc_fragment_re.search(f.path)
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
            'text': f'No files matching {_tc_fragment_re} pattern added',
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
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    logger.info('got %s event', event.event)
    logger.info('gh_api=%s', gh_api)


async def compile_towncrier_fragments_regex(ref):
    """Create fragments check regex based on the towncrier config."""
    fallback_base_dir = 'news'
    fallback_change_types = (
        'bugfix',
        'doc',
        'feature',
        'removal',
        'trivial',
        'vendor',
    )

    towncrier_conf = await get_towncrier_config(ref=ref) or {}
    base_dir = (
        towncrier_conf.get('directory', '').rstrip('/')
        or fallback_base_dir
    )
    change_types = (
        tuple(t['directory'] for t in towncrier_conf.get('type', ()))
        or fallback_change_types
    )

    # Ref:
    # * github.com/hawkowl/towncrier/blob/ecd438c/src/towncrier/_builder.py#L58
    return re.compile(
        (
            r'{base_dir}/{file_pattern}'
            r'(?P<fragment_type>{fragment_types})'
            r'{number_pattern}'
            r'{suffix_pattern}'
            r'$'
        ).format(
            base_dir=base_dir,
            file_pattern=r'(?P<issue_number>[^\./]+)\.',  # should we enforce?
            fragment_types=r'|'.join(change_types),
            number_pattern=r'(\.\d+)?',  # better be a number
            suffix_pattern=r'(\.[^\./]+)*',  # can we enforce ext per repo?
        ),
    )
