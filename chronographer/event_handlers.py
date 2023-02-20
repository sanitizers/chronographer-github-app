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
    LABEL_SKIP,
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
    pr_author = pull_request['user']
    pr_labels = {label['name'] for label in pull_request['labels']}
    diff_url = (
        f'https://github.com/{repo_slug}'
        f'/pull/{pull_request["number"]:d}.diff'
    )
    head_branch = pull_request['head']['ref']
    head_sha = pull_request['head']['sha']

    gh_api = RUNTIME_CONTEXT.app_installation_client

    repo_config = await get_chronographer_config(ref=head_sha)
    action_hints_config = repo_config.get('action-hints', {})
    checks_api_name = repo_config.get(
        'branch-protection-check-name',
        'Timeline protection',
    )

    checks_summary_epilogue = ''

    inline_markdown = action_hints_config.get('inline-markdown')
    if inline_markdown is not None:
        checks_summary_epilogue += f"""

        {inline_markdown!s}
        """

    external_docs_url = action_hints_config.get('external-docs-url')
    if external_docs_url is not None:
        checks_summary_epilogue += f"""

        Please, refer to the following document for more details on how to
        craft a great change note for inclusion with your pull request:
        {external_docs_url!s}
        """

    if LABEL_SKIP in pr_labels:
        logger.info(
            'Skipping PR event because the `%s` label is present',
            LABEL_SKIP,
        )
        await gh_api.post(
            check_runs_base_uri,
            preview_api_version='antiope',
            data=to_gh_query(NewCheckRequest(
                head_branch, head_sha,
                name=checks_api_name,
                status='completed',
                started_at=f'{datetime.utcnow().isoformat()}Z',
                completed_at=f'{datetime.utcnow().isoformat()}Z',
                conclusion='neutral',
                output={
                    'title':
                        f'{checks_api_name!s}: '
                        'Nothing to do — change note not required',
                    'text': f'Labels: {", ".join(pr_labels)}',
                    'summary':
                        'Heeeeey!'
                        '\n\n'
                        f'This PR has the `{LABEL_SKIP}` label meaning that '
                        'the maintainers do not expect a change note in this '
                        'pull request but you are still welcome to add one if '
                        'you feel like it may be useful in the '
                        'user-facing 📝 changelog.'
                        f'{checks_summary_epilogue!s}',
                },
            )),
        )
        return  # Interrupt the webhook event processing

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
                name=checks_api_name,
                status='completed',
                started_at=f'{datetime.utcnow().isoformat()}Z',
                completed_at=f'{datetime.utcnow().isoformat()}Z',
                conclusion='neutral',
                output={
                    'title': f'{checks_api_name!s}: Nothing to do',
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
                        '/blue-robot-vector-art.png)'
                        f'{checks_summary_epilogue!s}',
                },
            )),
        )
        return  # Interrupt the webhook event processing

    resp = await gh_api.post(
        check_runs_base_uri,
        preview_api_version='antiope',
        data=to_gh_query(NewCheckRequest(
            head_branch, head_sha,
            name=checks_api_name,
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

    towncrier_config = await get_towncrier_config(ref=head_sha) or {}

    update_check_req = UpdateCheckRequest(
        name=checks_api_name,
        status='in_progress',
    )
    resp = await gh_api.patch(
        check_runs_updates_uri,
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    enforce_name_key = (
        'enforce-name' if 'enforce-name' in repo_config
        else 'enforce_name'
    )
    _tc_fragment_re = await compile_towncrier_fragments_regex(
        name_settings=repo_config.get(enforce_name_key, {}),
        towncrier_config=towncrier_config,
    )

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

    news_fragments_required = requires_changelog(
        diff,
        _tc_fragment_re,
        repo_config.get('paths', {}),
        towncrier_config=towncrier_config,
    )

    report_success = not news_fragments_required or news_fragments_added

    update_check_req = attr.evolve(
        update_check_req,
        status='completed',
        conclusion='success' if news_fragments_added else
        'neutral' if not news_fragments_required else 'failure',
        completed_at=f'{datetime.utcnow().isoformat()}Z',
        output={
            # Fragments added
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
                '/wp-content/uploads/2014/10/vatican-library.jpg)'
                f'{checks_summary_epilogue!s}',
        } if report_success else {
            # Fragments not added and not required either
            'title':
                f'{update_check_req.name}: '
                'Nothing to do — change note not required',
            'summary':
                'This PR looks like a release preparation meaning that '
                'it removes the existing change notes and adds them to '
                'the user-facing 📝 changelog.'
                '\n\n'
                'Normally, such changes do not expect a change notes '
                'so you do not need to worry about adding one.'
                f'{checks_summary_epilogue!s}',
        } if not news_fragments_required else {
            # Fragments not added but are expected
            'title': f'{update_check_req.name}: History fragments missing',
            'text': f'No files matching {_tc_fragment_re} pattern added',
            'summary':
                'Oops... This change does not have a record in the '
                'archives. Just as if it never happened!'
                '\n\n'
                '![Keeping chronicles is important]('
                'https://theeventchronicle.com'
                '/wp-content/uploads/2014/10/vatlib7.jpg)'
                f'{checks_summary_epilogue!s}',
        },
    )
    resp = await gh_api.patch(
        check_runs_updates_uri,
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    logger.info('got %s event', event.event)
    logger.info('gh_api=%s', gh_api)


async def compile_towncrier_fragments_regex(name_settings, towncrier_config):
    """Create fragments check regex based on the towncrier config."""
    fallback_base_dir = 'news'

    # e.g. ``.rst``:
    fragment_filename_suffix = re.escape(name_settings.get('suffix', ''))

    base_dir = (
        towncrier_config.get('directory', '').rstrip('/')
        or fallback_base_dir
    )
    change_types = (
        tuple(t['directory'] for t in towncrier_config.get('type', ()))
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


def is_a_release_pr(diff, tc_fragment_re, towncrier_config):
    """Detect whether the current PR is a release.

    The heuristic is simply checking if the PR has additions to the
    changelog file combined with removal of the old change fragments.
    """
    fallback_changelog_filename = 'NEWS.rst'

    changelog_filename = (
        towncrier_config.get('filename', '')
        or fallback_changelog_filename
    )

    any_change_fragments_removed = False
    changelog_file_added = False

    for file_entry in diff:
        if not changelog_file_added and file_entry.path == changelog_filename:
            changelog_file_added = bool(file_entry.added)

        if (
                not any_change_fragments_removed
                and file_entry.is_removed_file
                and tc_fragment_re.search(file_entry.path)
        ):
            any_change_fragments_removed = True

        if any_change_fragments_removed and changelog_file_added:
            return True

    return False


def requires_changelog(diff, tc_fragment_re, config_paths, towncrier_config):
    """Check whether a changelog fragment is needed for the changes."""
    is_release = is_a_release_pr(
        diff, tc_fragment_re, towncrier_config=towncrier_config,
    )
    if is_release:
        return False

    file_paths = (f.path for f in diff)

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
