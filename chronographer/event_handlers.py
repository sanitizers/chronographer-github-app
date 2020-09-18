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

from .file_utils import (
    get_chronographer_config,
    get_towncrier_config,
)
from .labels import (
    LABEL_PROVIDED,
)

try:
    from towncrier._settings import _default_types as _towncrier_default_types
    FALLBACK_CHANGE_TYPES = tuple(_towncrier_default_types)
except ImportError:
    FALLBACK_CHANGE_TYPES = (
        'bugfix',
        'doc',
        'feature',
        'misc',
        'removal',
        'trivial',
        'vendor',
    )


logger = logging.getLogger(__name__)


import asyncio

@process_event('ping')
@process_webhook_payload
async def on_ping0(*, hook, hook_id, zen):
    await asyncio.sleep(1)
    print('ping0')


@process_event('ping')
@process_webhook_payload
async def on_ping1(*, hook, hook_id, zen):
    await asyncio.sleep(3)
    print('ping1')


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
# pylint: disable=too-many-locals
async def on_pr(event):
    """React to GitHub App pull request webhook event."""
    repo_slug = event.payload['repository']['full_name']
    check_runs_base_uri = f'/repos/{repo_slug}/check-runs'
    if event.name == 'pull_request':
        pull_request = event.payload['pull_request']
    elif event.name == 'check_run':
        pull_request = (
            event.payload['check_run']['check_suite']['pull_requests'][0]
        )
    elif event.name == 'check_suite':
        pull_request = (
            event.payload['check_suite']['pull_requests'][0]
        )
    pr_author = pull_request['user']
    diff_url = (
        f'https://github.com/{repo_slug}'
        f'/pull/{pull_request["number"]:d}.diff'
    )
    head_branch = pull_request['head']['ref']
    head_sha = pull_request['head']['sha']
    # head_sha = pull_request['merge_commit_sha']

    gh_api = RUNTIME_CONTEXT.app_installation_client

    repo_config = await get_chronographer_config(ref=head_sha)
    if is_blacklisted(pr_author, repo_config.get('exclude', {})):
        logger.info(
            'Skipping this event because %s is blacklisted',
            pr_author['login'],
        )
        await gh_api.post(
            check_runs_base_uri,
            preview_api_version='antiope',
            data=to_gh_query(NewCheckRequest(
                head_branch, head_sha,
                name='Timeline protection',
                status='completed',
                started_at=f'{datetime.utcnow().isoformat()}Z',
                completed_at=f'{datetime.utcnow().isoformat()}Z',
                conclusion='neutral',
                output={
                    'title': 'Timeline protection: Nothing to do',
                    'text':
                        'The author of this change '
                        f"({pr_author['login']!s}) "
                        'is ignored because it is excluded '
                        'via the repository config.',
                    'summary':
                        'Heeeeey!'
                        "We've got an inclusive and welcoming community here."
                        '\n\n'
                        'All robots 🤖 are welcome to send PRs, '
                        'no strings attached! '
                        'This change does not need to be recorded '
                        'to our chronicles.'
                        '\n\n'
                        '![Helloooo!]('
                        'https://www.goodfreephotos.com/albums/vector-images'
                        '/blue-robot-vector-art.png)',
                },
            )),
        )
        return  # Interrupt the webhook event processing

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

    _tc_fragment_re = await compile_towncrier_fragments_regex(
        ref=head_sha,
        name_settings=repo_config.get('enforce_name', {}),
    )

    news_fragments_required = True
    news_fragments_added = [
        f for f in diff
        if f.is_added_file and _tc_fragment_re.search(f.path)
    ]
    logger.info(
        'News fragments are %s',
        'present' if news_fragments_added
        else 'absent',
    )

    if news_fragments_added:
        labels_url = f'{pull_request["issue_url"]}/labels'
        await gh_api.post(
            labels_url,
            preview_api_version='symmetra',
            data={
                'labels': [
                    LABEL_PROVIDED,
                ],
            },
        )

    if not news_fragments_added and not requires_changelog(
            (f.path for f in diff),
            repo_config.get('paths', {}),
    ):
        news_fragments_required = False

    report_success = news_fragments_required and news_fragments_added

    update_check_req = attr.evolve(
        update_check_req,
        status='completed',
        conclusion='success' if report_success else 'failure',
        completed_at=f'{datetime.utcnow().isoformat()}Z',
        output={
            'title': f'{update_check_req.name}: Good to go',
            'text':
                'The following news fragments found: '
                f'{news_fragments_added!r}'
                '\n\n'
                f'Pattern: {_tc_fragment_re}',
            'summary':
                'Great! This change has been recorded to the chronicles'
                '\n\n'
                '![You are good at keeping records!]('
                'https://theeventchronicle.com'
                '/wp-content/uploads/2014/10/vatican-library.jpg)',
        } if report_success else {
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

    logger.info('got %s event', event.name)
    logger.info('gh_api=%s', gh_api)


async def compile_towncrier_fragments_regex(ref, name_settings):
    """Create fragments check regex based on the towncrier config."""
    fallback_base_dir = 'news'

    # e.g. ``.rst``:
    fragment_filename_suffix = re.escape(name_settings.get('suffix', ''))

    towncrier_conf = await get_towncrier_config(ref=ref) or {}
    base_dir = (
        towncrier_conf.get('directory', '').rstrip('/')
        or fallback_base_dir
    )
    change_types = (
        tuple(t['directory'] for t in towncrier_conf.get('type', ()))
        or FALLBACK_CHANGE_TYPES
    )

    # Ref:
    # * github.com/hawkowl/towncrier/blob/ecd438c/src/towncrier/_builder.py#L58
    return re.compile(
        (
            r'{base_dir}/{file_pattern}'
            r'(?P<fragment_type>{fragment_types})'
            r'{number_pattern}'
            r'{suffix_pattern}'
            r'{postfix_pattern}'
            r'$'
        ).format(
            base_dir=base_dir,
            file_pattern=r'(?P<issue_number>[^\./]+)\.',  # should we enforce?
            fragment_types=r'|'.join(change_types),
            number_pattern=r'(\.\d+)?',  # better be a number
            suffix_pattern=r'(\.[^\./]+)*',
            postfix_pattern=fragment_filename_suffix,
        ),
    )


def is_blacklisted(actor, blacklist):
    """Find out if the given actor is blacklisted."""
    bot_suffix_length = 5
    username = actor['login']
    blacklist_bots = blacklist.get('bots', True)
    if blacklist_bots and actor['type'] == 'Bot':
        username = username[:-bot_suffix_length]  # Strip off ``[bot]`` suffix
        try:
            return username in blacklist_bots
        except TypeError:
            return True

    blacklist_humans = blacklist.get('humans', False)
    if blacklist_humans and actor['type'] == 'User':
        try:
            return username in blacklist_humans
        except TypeError:
            return True

    return False


def requires_changelog(file_paths, config_paths):
    """Check whether a changelog fragment is needed for the changes."""
    include_paths = config_paths.get('include', [])
    exclude_paths = config_paths.get('exclude', [])

    paths_gen = (p for p in file_paths)

    if include_paths:
        paths_gen = (
            p for p in paths_gen
            if any(p.startswith(i) for i in include_paths)
        )

    if exclude_paths:
        paths_gen = (
            p for p in paths_gen
            if not any(p.startswith(e) for e in exclude_paths)
        )

    return next(paths_gen, False) is not False
