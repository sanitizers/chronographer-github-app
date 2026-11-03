"""Webhook event handlers."""
import base64
from datetime import datetime
from io import StringIO
import logging
import re

import attr
import gidgethub
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


CHECKS_SUMMARY_EPILOGUE_INTRO = """
Please, refer to the following document for more details on how to
craft a great change note for inclusion with your pull request:
"""

# Identifier namespace of the "create a change note" check run buttons:
CHANGE_NOTE_ACTION_PREFIX = 'mkfrag:'

# The closing keywords GitHub itself recognises in a pull request body,
# followed by any of the issue references it accepts:
CLOSING_KEYWORDS_RE = re.compile(
    r'\b(?:clos(?:e|es|ed)|fix(?:es|ed)?|resolv(?:e|es|ed))\b\s*:?\s*'
    r'(?:'
    r'(?P<slug>[\w.-]+/[\w.-]+)?\#'
    r'|GH-'
    r'|https?://github\.com/(?P<url_slug>[\w.-]+/[\w.-]+)/issues/'
    r')'
    r'(?P<number>\d+)\b',
    re.IGNORECASE,
)

# The Checks API caps a check run at three actions and every action
# identifier at 20 characters:
MAX_CHECK_RUN_ACTIONS = 3
MAX_CHANGE_TYPE_LENGTH = 20 - len(CHANGE_NOTE_ACTION_PREFIX)


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
# This handler is long enough to trip both size checks and wants a
# split, which is a refactor of its own:
# pylint: disable=too-many-locals,too-many-statements
async def on_pr(event):
    """React to GitHub App pull request webhook event."""
    event_repository = event.data['repository']
    repo_slug = event_repository['full_name']
    check_runs_base_uri = f'/repos/{repo_slug}/check-runs'

    gh_api = RUNTIME_CONTEXT.app_installation_client

    pull_request = await resolve_pull_request(event, repo_slug, gh_api)
    if pull_request is None:
        return  # Interrupt the webhook event processing

    pr_author = pull_request['user']
    pr_labels = {label['name'] for label in pull_request['labels']}
    pr_labels_list = ', '.join(pr_labels)
    pr_number = pull_request['number']
    diff_url = (
        f'https://github.com/{repo_slug}'
        f'/pull/{pr_number:d}.diff'
    )
    head_branch = pull_request['head']['ref']
    head_sha = pull_request['head']['sha']
    repo_default_branch = event_repository['default_branch']

    repo_config = await get_chronographer_config(ref=repo_default_branch)
    paths_config = repo_config.get(
        'paths',
        {'towncrier-config-filename': None},
    )
    action_hints_config = repo_config.get('action-hints', {})
    checks_api_name = repo_config.get(
        'branch-protection-check-name',
        'Timeline protection',
    )
    checks_summary_title_prefix = action_hints_config.get(
        'check-title-prefix',
        f'{checks_api_name!s}: ',
    )

    checks_summary_epilogue = ''

    inline_markdown = action_hints_config.get('inline-markdown')
    if inline_markdown is not None:
        checks_summary_epilogue += '\n'.join(('', '', inline_markdown))

    external_docs_url = action_hints_config.get('external-docs-url')
    if external_docs_url is not None:
        checks_summary_epilogue += ''.join((
            CHECKS_SUMMARY_EPILOGUE_INTRO,
            external_docs_url,
        ))

    labels_config = repo_config.get('labels', {})
    fragment_provided_label = labels_config.get(
        'fragment-provided',
        LABEL_PROVIDED,
    )
    repo_skip_label = labels_config.get('skip-changelog', LABEL_SKIP)

    logger.info(
        'Checking if `%s` label is present among these PR labels: `%s`.',
        repo_skip_label,
        pr_labels_list or 'NO LABELS',
    )
    if repo_skip_label in pr_labels:
        logger.info(
            'Skipping PR event because the `%s` label is present',
            repo_skip_label,
        )
        await gh_api.post(
            check_runs_base_uri,
            preview_api_version='antiope',
            data=to_gh_query(
                NewCheckRequest(
                    head_branch, head_sha,
                    name=checks_api_name,
                    status='completed',
                    started_at=f'{datetime.utcnow().isoformat()}Z',
                    completed_at=f'{datetime.utcnow().isoformat()}Z',
                    conclusion='neutral',
                    output={
                        'title':
                            f'{checks_summary_title_prefix!s}'
                            'Nothing to do — change note not required',
                        'text': f'Labels: {pr_labels_list!s}',
                        'summary':
                            'Heeeeey!'
                            '\n\n'
                            f'This PR has the `{repo_skip_label}` label '
                            'meaning that the maintainers do not expect a '
                            'change note in this pull request but you are '
                            'still welcome to add one if you feel like it may '
                            'be useful in the user-facing 📝 changelog.'
                            f'{checks_summary_epilogue!s}',
                    },
                ),
            ),
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
            data=to_gh_query(
                NewCheckRequest(
                    head_branch, head_sha,
                    name=checks_api_name,
                    status='completed',
                    started_at=f'{datetime.utcnow().isoformat()}Z',
                    completed_at=f'{datetime.utcnow().isoformat()}Z',
                    conclusion='neutral',
                    output={
                        'title':
                        f'{checks_summary_title_prefix!s}Nothing to do',
                        'text':
                            'The author of this change '
                            f"({pr_author['login']!s}) "
                            'is ignored because it is excluded '
                            'via the repository config.',
                        'summary':
                            'Heeeeey!'
                            "We've got an inclusive and welcoming community "
                            'here.\n\n'
                            'All robots 🤖 are welcome to send PRs, '
                            'no strings attached! '
                            'This change does not need to be recorded '
                            'to our chronicles.'
                            '\n\n'
                            '![Helloooo!]('
                            'https://www.goodfreephotos.com/albums'
                            '/vector-images/blue-robot-vector-art.png)'
                            f'{checks_summary_epilogue!s}',
                    },
                ),
            ),
        )
        return  # Interrupt the webhook event processing

    resp = await gh_api.post(
        check_runs_base_uri,
        preview_api_version='antiope',
        data=to_gh_query(
            NewCheckRequest(
                head_branch, head_sha,
                name=checks_api_name,
                status='queued',
                started_at=f'{datetime.utcnow().isoformat()}Z',
            ),
        ),
    )
    logger.info(
        'Check suite ID is %s',
        resp['check_suite']['id'],
    )
    check_run_id = resp['id']
    logger.info(
        'Check run ID is %s',
        check_run_id,
    )
    check_runs_updates_uri = f'{check_runs_base_uri}/{check_run_id:d}'

    logger.info("Here's the diff URL: %s", diff_url)
    diff_text = await gh_api.getitem(
        diff_url,
    )
    logger.info("Here's the diff text: %s", diff_text)
    diff = PatchSet(StringIO(diff_text))
    logger.info("Here's the diff object: %r", diff)

    towncrier_config = await load_towncrier_config(
        repo_config,
        ref=head_sha or repo_default_branch,
    )

    update_check_req = UpdateCheckRequest(
        name=checks_api_name,
        status='in_progress',
    )
    resp = await gh_api.patch(
        check_runs_updates_uri,
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    _tc_fragment_re = await compile_towncrier_fragments_regex(
        name_settings=enforce_name_settings(repo_config),
        towncrier_config=towncrier_config,
    )

    news_fragments_added = [
        f for f in diff
        if f.is_added_file and _tc_fragment_re.search(f.path)
    ]
    news_fragment_types = {
        _tc_fragment_re.search(f.path).group('fragment_type')
        for f in news_fragments_added
    }
    logger.info(
        'News fragments are %s',
        'present' if news_fragments_added
        else 'absent',
    )

    if news_fragments_added and fragment_provided_label is not None:
        issue_url = pull_request['issue_url']
        labels_url = f'{issue_url!s}/labels'
        await gh_api.post(
            labels_url,
            preview_api_version='symmetra',
            data={
                'labels': [
                    fragment_provided_label,
                ],
            },
        )

    news_fragments_required = requires_changelog(
        diff,
        _tc_fragment_re,
        paths_config,
        towncrier_config=towncrier_config,
    )

    change_type_requirements = repo_config.get('require-change-types') or {}
    label_origins = (
        await collect_requirement_labels(
            gh_api,
            repo_slug=repo_slug,
            pull_request=pull_request,
            requirements=change_type_requirements,
        )
        if repo_config.get('infer-labels-from-linked-issues', False)
        else dict.fromkeys(pr_labels)
    )

    unmet_change_type_requirements = find_unmet_change_type_requirements(
        label_origins.keys(),
        change_type_requirements,
        news_fragment_types,
    )

    demanded_change_types = sorted({
        change_type
        for accepted_types in unmet_change_type_requirements.values()
        for change_type in as_change_type_set(accepted_types)
    })

    conclusion, check_output = build_check_result(
        title_prefix=checks_summary_title_prefix,
        epilogue=checks_summary_epilogue,
        fragments_added=news_fragments_added,
        fragments_required=news_fragments_required,
        fragment_re=_tc_fragment_re,
        unmet_change_type_requirements=unmet_change_type_requirements,
        label_origins=label_origins,
    )

    update_check_req = attr.evolve(
        update_check_req,
        status='completed',
        conclusion=conclusion,
        completed_at=f'{datetime.utcnow().isoformat()}Z',
        output=check_output,
        # Only a failing run has something for the maintainer to fix, so
        # that is the only one worth putting buttons on:
        actions=build_change_note_actions(
            demanded_types=demanded_change_types,
            known_types=change_note_types(towncrier_config),
        ) if conclusion == 'failure' else [],
    )
    resp = await gh_api.patch(
        check_runs_updates_uri,
        preview_api_version='antiope',
        data=to_gh_query(update_check_req),
    )

    logger.info('got %s event', event.event)
    logger.info('gh_api=%s', gh_api)


@process_event_actions('check_run', {'requested_action'})
async def on_change_note_requested(event):
    """Commit the change note a check run button asks for."""
    requested_action = event.data['requested_action']['identifier']
    if not requested_action.startswith(CHANGE_NOTE_ACTION_PREFIX):
        logger.info(
            'Ignoring the unknown requested action `%s`',
            requested_action,
        )
        return

    change_type = requested_action[len(CHANGE_NOTE_ACTION_PREFIX):]

    event_repository = event.data['repository']
    repo_slug = event_repository['full_name']
    gh_api = RUNTIME_CONTEXT.app_installation_client

    pull_request = await resolve_pull_request(event, repo_slug, gh_api)
    if pull_request is None:
        return  # Interrupt the webhook event processing

    head = pull_request['head']
    repo_config = await get_chronographer_config(
        ref=event_repository['default_branch'],
    )
    towncrier_config = await load_towncrier_config(
        repo_config,
        ref=head['sha'] or event_repository['default_branch'],
    )

    # The identifier comes back from GitHub rather than from the click, but
    # a fragment of an unknown type would not satisfy the check anyway --
    # and this keeps a forged payload from naming a path of its choosing:
    if change_type not in change_note_types(towncrier_config):
        logger.info(
            'Refusing to create a `%s` change note because towncrier '
            'does not accept that type',
            change_type,
        )
        return

    if head['repo'] is None:
        await report_change_note_failure(
            event, gh_api, repo_slug,
            reason='the head repository of this pull request is gone',
        )
        return

    pr_title = pull_request['title']
    fragment_path = change_note_path(
        repo_config=repo_config,
        towncrier_config=towncrier_config,
        change_type=change_type,
        pr_number=pull_request['number'],
    )
    logger.info('Creating `%s` on `%s`', fragment_path, head['ref'])
    try:
        await commit_change_note(
            gh_api,
            head=head,
            path=fragment_path,
            # An actually empty file would give the pull request
            # participants no line to attach a suggested change to, so
            # seed it with the title:
            text=f'{pr_title!s}\n',
            message=f'📝 Add an empty {change_type!s} change note',
        )
    except gidgethub.HTTPException as commit_error:
        logger.info(
            'Failed to create `%s`, GitHub said %s',
            fragment_path,
            commit_error.status_code,
        )
        await report_change_note_failure(
            event, gh_api, repo_slug,
            reason=f'pushing `{fragment_path!s}` to the head branch failed',
        )
        return

    # The push makes GitHub send a ``synchronize`` event, and the check run
    # it starts reports on the change note that just landed.  Nothing left
    # to say here.
    logger.info('Created `%s`', fragment_path)


async def load_towncrier_config(repo_config, *, ref):
    """Fetch the towncrier config the repository config points at."""
    paths_config = repo_config.get(
        'paths',
        {'towncrier-config-filename': None},
    )
    return await get_towncrier_config(
        towncrier_config_filename=paths_config.get(
            'towncrier-config-filename',
            None,
        ),
        ref=ref,
    ) or {}


def change_note_path(
        *, repo_config, towncrier_config, change_type, pr_number,
):
    """Return the path towncrier expects this change note at."""
    base_dir = change_note_base_dir(towncrier_config)
    suffix = enforce_name_settings(repo_config).get('suffix', '')
    return f'{base_dir!s}/{pr_number:d}.{change_type!s}{suffix!s}'


async def commit_change_note(gh_api, *, head, path, text, message):
    """Add a file to the head branch of a pull request."""
    head_slug = head['repo']['full_name']
    await gh_api.put(
        f'/repos/{head_slug!s}/contents/{path!s}',
        data={
            'branch': head['ref'],
            'content': base64.b64encode(text.encode()).decode(),
            'message': message,
        },
    )


async def report_change_note_failure(event, gh_api, repo_slug, *, reason):
    """Tell the check run why its button did not produce a change note."""
    check_run = event.data['check_run']
    check_run_id = check_run['id']
    now = f'{datetime.utcnow().isoformat()}Z'
    await gh_api.patch(
        f'/repos/{repo_slug}/check-runs/{check_run_id:d}',
        preview_api_version='antiope',
        data=to_gh_query(
            UpdateCheckRequest(
                name=check_run['name'],
                status='completed',
                conclusion='failure',
                completed_at=now,
                output={
                    'title': 'Could not create the change note',
                    'summary':
                        'Sorry! The change note you asked for did not '
                        f'happen because {reason!s}.'
                        '\n\n'
                        'Adding the file by hand works just as well.',
                },
            ),
        ),
    )


async def resolve_pull_request(event, repo_slug, gh_api):
    """Look up the full pull request payload an event points at.

    ``pull_request`` events carry it inline.  The Checks API only
    embeds stub pull request objects that lack ``user``, ``labels``
    and ``issue_url`` -- and it leaves that list empty altogether when
    the head branch lives in a fork -- so re-requested checks need an
    extra round trip.

    Returns ``None`` when no pull request is associated with the event.
    """
    if event.event == 'pull_request':
        return event.data['pull_request']

    check_suite = (
        event.data['check_run']['check_suite'] if event.event == 'check_run'
        else event.data['check_suite']
    )

    pull_request_stubs = check_suite['pull_requests']
    if pull_request_stubs:
        pr_number = pull_request_stubs[0]['number']
        return await gh_api.getitem(f'/repos/{repo_slug}/pulls/{pr_number:d}')

    # Fork head branches never show up in ``pull_requests``, but the
    # head commit still knows which pull requests it belongs to:
    head_sha = check_suite['head_sha']
    associated_pull_requests = await gh_api.getitem(
        f'/repos/{repo_slug}/commits/{head_sha}/pulls',
    )
    if associated_pull_requests:
        return associated_pull_requests[0]

    logger.info(
        'Skipping the %s event because no pull request is associated '
        'with the head commit %s',
        event.event,
        head_sha,
    )
    return None


def find_linked_issue_numbers(pr_body, repo_slug):
    """Return the same-repo issues a pull request body says it closes.

    Only the closing keywords spelled out in the description are
    visible here -- an issue attached through the sidebar is reported
    by the GraphQL API alone.  Cross-repository references are dropped
    too, because the App is not necessarily installed on the other end.
    """
    return sorted({
        int(match['number'])
        for match in CLOSING_KEYWORDS_RE.finditer(pr_body or '')
        if (match['slug'] or match['url_slug'] or repo_slug).lower()
        == repo_slug.lower()
    })


async def collect_requirement_labels(
        gh_api, *, repo_slug, pull_request, requirements,
):
    """Map every label that gets a vote to where it was picked up.

    The pull request's own labels always count and map to ``None``.  One
    that already carries a label the config votes on speaks for itself,
    so the issues it closes are consulted only when it carries none of
    them -- those issues tend to be high-level and to span several pull
    requests, which would make their labels the louder voice.
    """
    label_origins = {
        label['name']: None for label in pull_request['labels']
    }
    if label_origins.keys() & requirements.keys():
        return label_origins

    for issue_number in find_linked_issue_numbers(
            pull_request['body'], repo_slug,
    ):
        try:
            linked_issue = await gh_api.getitem(
                f'/repos/{repo_slug!s}/issues/{issue_number:d}',
            )
        except gidgethub.HTTPException as lookup_error:
            logger.info(
                'Ignoring the linked issue #%d, GitHub said %s',
                issue_number,
                lookup_error.status_code,
            )
            continue

        for label in linked_issue['labels']:
            label_origins.setdefault(label['name'], issue_number)

    return label_origins


def find_unmet_change_type_requirements(
        labels, requirements, fragment_types,
):
    """Map each demanding label to the change types no fragment covers.

    ``requirements`` comes straight out of the repository config and
    maps a label name to the change types that satisfy it.  A label
    contributes a requirement only while it applies to the pull request,
    and a single fragment of any of the listed types settles it.
    """
    return {
        label: accepted_types
        for label, accepted_types in requirements.items()
        if label in labels
        and not fragment_types & as_change_type_set(accepted_types)
    }


def label_origin_note(label_origins, label):
    """Name the linked issue a demanding label was inherited from."""
    issue_number = (label_origins or {}).get(label)
    return '' if issue_number is None else f' (from #{issue_number:d})'


def as_change_type_set(accepted_types):
    """Normalise one config entry into a set of change type names."""
    return (
        {accepted_types} if isinstance(accepted_types, str)
        else set(accepted_types)
    )


# Every argument here is keyword-only and names one independent input of
# the rendered check run, so bundling them would only add indirection:
# pylint: disable-next=too-many-arguments
def build_check_result(
        *, title_prefix, epilogue, fragments_added, fragments_required,
        fragment_re, unmet_change_type_requirements=None,
        label_origins=None,
):
    """Compose the Checks API conclusion and output for a scanned PR."""
    if fragments_added and unmet_change_type_requirements:
        demands = '\n'.join(
            f'* `{label!s}`'
            f'{label_origin_note(label_origins, label)!s} '
            'wants a change note of type '
            + ' or '.join(
                f'`{change_type!s}`'
                for change_type in sorted(as_change_type_set(accepted_types))
            )
            for label, accepted_types in sorted(
                unmet_change_type_requirements.items(),
            )
        )
        return 'failure', {
            'title':
                f'{title_prefix!s}'
                'History fragments of the wrong type',
            'text':
                'The following news fragments found: '
                f'{fragments_added!r}'
                '\n\n'
                f'Pattern: {fragment_re}',
            'summary':
                'Close! This change is recorded, but its labels ask for '
                'a different kind of change note:'
                '\n\n'
                f'{demands!s}'
                f'{epilogue!s}',
        }

    if fragments_added:
        return 'success', {
            'title': f'{title_prefix!s}Good to go',
            'text':
                'The following news fragments found: '
                f'{fragments_added!r}'
                '\n\n'
                f'Pattern: {fragment_re}',
            'summary':
                'Great! This change has been recorded to the chronicles'
                '\n\n'
                '![You are good at keeping records! '
                'Image source: Unsplash ID=bByhWydZLW0]'
                '(https://source.unsplash.com/bByhWydZLW0/1600x500)'
                f'{epilogue!s}',
        }

    if not fragments_required:
        return 'neutral', {
            'title':
                f'{title_prefix!s}'
                'Nothing to do — change note not required',
            'summary':
                'This PR looks like a release preparation meaning that '
                'it removes the existing change notes and adds them to '
                'the user-facing 📝 changelog.'
                '\n\n'
                'Normally, such changes do not expect a change notes '
                'so you do not need to worry about adding one.'
                f'{epilogue!s}',
        }

    return 'failure', {
        'title':
            f'{title_prefix!s}'
            'History fragments missing',
        'text': f'No files matching {fragment_re} pattern added',
        'summary':
            'Oops... This change does not have a record in the '
            'archives. Just as if it never happened!'
            '\n\n'
            '![Keeping chronicles is important! '
            'Image source: Unsplash ID=VSE71nAZhU8]'
            '(https://source.unsplash.com/VSE71nAZhU8/1600x500)'
            f'{epilogue!s}',
    }


def change_note_base_dir(towncrier_config):
    """Return the directory towncrier keeps change note fragments in."""
    fallback_base_dir = 'news'
    return (
        towncrier_config.get('directory', '').rstrip('/')
        or fallback_base_dir
    )


def change_note_types(towncrier_config):
    """Return the change note types towncrier accepts, in config order."""
    return (
        tuple(t['directory'] for t in towncrier_config.get('type', ()))
        or FALLBACK_CHANGE_TYPES
    )


def enforce_name_settings(repo_config):
    """Return the ``enforce-name`` section, tolerating its old spelling."""
    enforce_name_key = (
        'enforce-name' if 'enforce-name' in repo_config
        else 'enforce_name'
    )
    return repo_config.get(enforce_name_key, {})


def build_change_note_actions(*, demanded_types, known_types):
    """Offer up to three buttons creating an empty change note.

    The Checks API only fits three actions on a check run, so the types
    the pull request labels actually ask for come first and the ones
    towncrier merely knows about fill whatever room is left.

    Types towncrier does not know are dropped: a fragment of such a type
    would not satisfy the very check offering to create it.  So are types
    too long to name in an action identifier.
    """
    candidates = [
        change_type for change_type in demanded_types
        if change_type in known_types
    ]
    candidates += [
        change_type for change_type in known_types
        if change_type not in candidates
    ]
    return [
        {
            'label': change_type,
            'description': f'Add an empty {change_type!s} change note',
            'identifier': f'{CHANGE_NOTE_ACTION_PREFIX!s}{change_type!s}',
        }
        for change_type in candidates
        if len(change_type) <= MAX_CHANGE_TYPE_LENGTH
    ][:MAX_CHECK_RUN_ACTIONS]


async def compile_towncrier_fragments_regex(name_settings, towncrier_config):
    """Create fragments check regex based on the towncrier config."""
    # The named placeholders below document what each chunk of the regex is
    # for, which an f-string would not:
    # pylint: disable=consider-using-f-string
    # e.g. ``.rst``:
    fragment_filename_suffix = re.escape(name_settings.get('suffix', ''))

    base_dir = change_note_base_dir(towncrier_config)
    change_types = change_note_types(towncrier_config)

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
