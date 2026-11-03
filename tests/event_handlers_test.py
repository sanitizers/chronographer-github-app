"""Tests for the helpers backing the webhook event handlers."""

import asyncio
import base64
from http import HTTPStatus
from types import SimpleNamespace

import gidgethub
import pytest

from octomachinery.github.models.checks_api_requests import (
    UpdateCheckRequest,
)

from chronographer import event_handlers
from chronographer.event_handlers import (
    build_change_note_actions,
    build_check_result,
    change_note_base_dir,
    change_note_types,
    enforce_name_settings,
    collect_requirement_labels,
    compile_towncrier_fragments_regex,
    find_linked_issue_numbers,
    find_unmet_change_type_requirements,
    is_a_release_pr,
    is_blacklisted,
    requires_changelog,
    resolve_pull_request,
)

from .conftest import (
    ADDED_FRAGMENT_DIFF,
    FakeGitHubAPI,
    CHANGELOG_ADDITION_DIFF,
    make_event,
    REMOVED_FRAGMENT_DIFF,
    SOURCE_CHANGE_DIFF,
)


def make_fragment_re(name_settings=None, towncrier_config=None):
    """Compile the fragment regex outside of an async context."""
    return asyncio.run(
        compile_towncrier_fragments_regex(
            name_settings=name_settings or {},
            towncrier_config=towncrier_config or {},
        ),
    )


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('news/123.bugfix', True),
        ('news/123.feature', True),
        ('news/some-slug.doc', True),
        ('news/123.bugfix.1', True),
        ('news/123.bugfix.rst', True),
        ('news/123.unknown', False),
        ('docs/123.bugfix', False),
        ('news/123', False),
    ],
)
def test_default_fragment_pattern(path, expected):
    """Check the default ``news/`` layout against known good and bad paths."""
    assert bool(make_fragment_re().search(path)) is expected


def test_fragment_pattern_captures_the_change_type():
    """Check that the pattern names the type driving the label rules."""
    assert make_fragment_re().search(
        'news/123.bugfix.rst',
    ).group('fragment_type') == 'bugfix'


def test_fragment_pattern_honours_towncrier_config():
    """Check that the towncrier directory and types drive the pattern."""
    fragment_re = make_fragment_re(
        towncrier_config={
            'directory': 'changelog.d/',
            'type': ({'directory': 'change'}, {'directory': 'breaking'}),
        },
    )

    assert fragment_re.search('changelog.d/42.change')
    assert fragment_re.search('changelog.d/42.breaking')
    assert not fragment_re.search('changelog.d/42.bugfix')
    assert not fragment_re.search('news/42.change')


def test_fragment_pattern_enforces_suffix():
    """Check that the configured suffix becomes mandatory."""
    fragment_re = make_fragment_re(name_settings={'suffix': '.rst'})

    assert fragment_re.search('news/42.bugfix.rst')
    assert not fragment_re.search('news/42.bugfix.md')


@pytest.mark.parametrize(
    ('actor', 'blacklist', 'expected'),
    [
        ({'login': 'dependabot[bot]', 'type': 'Bot'}, {}, True),
        ({'login': 'webknjaz', 'type': 'User'}, {}, False),
        (
            {'login': 'dependabot[bot]', 'type': 'Bot'},
            {'bots': False},
            False,
        ),
        (
            {'login': 'dependabot[bot]', 'type': 'Bot'},
            {'bots': ['dependabot']},
            True,
        ),
        (
            {'login': 'patchback[bot]', 'type': 'Bot'},
            {'bots': ['dependabot']},
            False,
        ),
        (
            {'login': 'pyup-bot', 'type': 'User'},
            {'humans': ['pyup-bot']},
            True,
        ),
        (
            {'login': 'webknjaz', 'type': 'User'},
            {'humans': ['pyup-bot']},
            False,
        ),
    ],
)
def test_is_blacklisted(actor, blacklist, expected):
    """Check that actors are excluded per the repository config."""
    assert is_blacklisted(actor, blacklist) is expected


def test_is_a_release_pr(make_diff):
    """Check that dropping fragments into the changelog reads as a release."""
    diff = make_diff(REMOVED_FRAGMENT_DIFF + CHANGELOG_ADDITION_DIFF)

    assert is_a_release_pr(diff, make_fragment_re(), towncrier_config={})


def test_changelog_addition_alone_is_not_a_release(make_diff):
    """Check that touching the changelog by itself is not a release."""
    diff = make_diff(CHANGELOG_ADDITION_DIFF)

    assert not is_a_release_pr(diff, make_fragment_re(), towncrier_config={})


def test_release_pr_does_not_require_a_changelog(make_diff):
    """Check that release PRs are exempt from the fragment requirement."""
    diff = make_diff(REMOVED_FRAGMENT_DIFF + CHANGELOG_ADDITION_DIFF)

    assert not requires_changelog(
        diff, make_fragment_re(), {}, towncrier_config={},
    )


def test_source_change_requires_a_changelog(make_diff):
    """Check that an ordinary code change expects a fragment."""
    assert requires_changelog(
        make_diff(SOURCE_CHANGE_DIFF),
        make_fragment_re(),
        {},
        towncrier_config={},
    )


@pytest.mark.parametrize(
    ('config_paths', 'expected'),
    [
        ({'include': ['src/']}, True),
        ({'include': ['docs/']}, False),
        ({'exclude': ['src/']}, False),
        ({'exclude': ['docs/']}, True),
        ({'include': ['src/'], 'exclude': ['src/app.py']}, False),
    ],
)
def test_requires_changelog_path_filters(make_diff, config_paths, expected):
    """Check that the include/exclude path filters gate the requirement."""
    assert requires_changelog(
        make_diff(SOURCE_CHANGE_DIFF),
        make_fragment_re(),
        config_paths,
        towncrier_config={},
    ) is expected


def test_check_result_reports_success_when_fragments_added():
    """Check that added fragments produce a successful check run."""
    conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='',
        fragments_added=['news/123.bugfix'],
        fragments_required=True,
        fragment_re='<re>',
    )

    assert conclusion == 'success'
    assert output['title'] == 'chng: Good to go'


def test_check_result_is_neutral_when_not_required():
    """Check that release PRs get the "nothing to do" output, not success.

    A fragment-less PR that does not need a fragment must not be
    reported as if a fragment had been found.
    """
    conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='',
        fragments_added=[],
        fragments_required=False,
        fragment_re='<re>',
    )

    assert conclusion == 'neutral'
    assert output['title'] == 'chng: Nothing to do — change note not required'
    assert 'release preparation' in output['summary']


def test_check_result_fails_when_fragments_missing():
    """Check that a missing but required fragment fails the check run."""
    conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='epilogue',
        fragments_added=[],
        fragments_required=True,
        fragment_re='<re>',
    )

    assert conclusion == 'failure'
    assert output['title'] == 'chng: History fragments missing'
    assert output['summary'].endswith('epilogue')


@pytest.mark.parametrize(
    ('pr_labels', 'fragment_types', 'expected'),
    [
        ({'enhancement'}, {'feature'}, {}),
        ({'enhancement'}, {'contrib'}, {}),
        ({'enhancement'}, {'bugfix'}, {'enhancement': ['contrib', 'feature']}),
        ({'unrelated'}, {'bugfix'}, {}),
        (set(), set(), {}),
        ({'enhancement'}, {'bugfix', 'feature'}, {}),
        (
            {'enhancement', 'bug'},
            {'feature'},
            {'bug': ['bugfix']},
        ),
    ],
)
def test_unmet_change_type_requirements(pr_labels, fragment_types, expected):
    """Check which labels are left wanting a different change note."""
    requirements = {
        'enhancement': ['contrib', 'feature'],
        'bug': ['bugfix'],
    }

    assert find_unmet_change_type_requirements(
        pr_labels, requirements, fragment_types,
    ) == expected


def test_change_type_requirement_accepts_a_bare_string():
    """Check that a single change type need not be wrapped in a list.

    ``{'bug': 'bugfix'}`` must not be read as a set of characters.
    """
    assert find_unmet_change_type_requirements(
        {'bug'}, {'bug': 'bugfix'}, {'b'},
    ) == {'bug': 'bugfix'}
    assert not find_unmet_change_type_requirements(
        {'bug'}, {'bug': 'bugfix'}, {'bugfix'},
    )


def test_check_result_fails_on_the_wrong_fragment_type():
    """Check that a fragment of an unwanted type fails the check run."""
    conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='epilogue',
        fragments_added=['news/123.bugfix'],
        fragments_required=True,
        fragment_re='<re>',
        unmet_change_type_requirements={
            'enhancement': ['contrib', 'feature'],
        },
    )

    assert conclusion == 'failure'
    assert output['title'] == 'chng: History fragments of the wrong type'
    assert '`enhancement`' in output['summary']
    assert '`contrib` or `feature`' in output['summary']
    assert output['summary'].endswith('epilogue')


def test_check_result_ignores_requirements_without_fragments():
    """Check that the plain "missing" failure wins over the type one.

    An unmet requirement is meaningless while no fragment exists at
    all -- telling the author their non-existent note is of the wrong
    type would be nonsense.
    """
    conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='',
        fragments_added=[],
        fragments_required=True,
        fragment_re='<re>',
        unmet_change_type_requirements={'enhancement': ['feature']},
    )

    assert conclusion == 'failure'
    assert output['title'] == 'chng: History fragments missing'


def test_added_fragment_is_detected(make_diff):
    """Check that a new fragment file is recognised in a diff."""
    fragment_re = make_fragment_re()
    diff = make_diff(ADDED_FRAGMENT_DIFF + SOURCE_CHANGE_DIFF)

    assert [
        patched_file.path for patched_file in diff
        if patched_file.is_added_file and fragment_re.search(patched_file.path)
    ] == ['news/123.bugfix']


PULL_REQUEST_PAYLOAD = {
    'number': 1,
    'user': {'login': 'webknjaz', 'type': 'User'},
    'labels': [],
    'head': {'ref': 'feature', 'sha': 'f2114ef'},
}


@pytest.mark.parametrize(
    'event_name',
    ['check_run', 'check_suite'],
)
def test_rerequested_check_fetches_the_full_pull_request(
        event_name, make_gh_api,
):
    """Check that embedded PR stubs get replaced by the real payload."""
    check_suite = {'head_sha': 'f2114ef', 'pull_requests': [{'number': 1}]}
    data = {
        'check_run': {'check_suite': check_suite},
    } if event_name == 'check_run' else {'check_suite': check_suite}
    pulls_url = '/repos/sanitizers/chronographer/pulls/1'
    gh_api = make_gh_api({pulls_url: PULL_REQUEST_PAYLOAD})

    pull_request = asyncio.run(
        resolve_pull_request(
            make_event(event_name, data),
            'sanitizers/chronographer',
            gh_api,
        ),
    )

    assert pull_request is PULL_REQUEST_PAYLOAD
    assert gh_api.requested_urls == [pulls_url]


def test_rerequested_check_from_a_fork_looks_up_the_head_commit(make_gh_api):
    """Check that an empty stub list falls back to the head commit."""
    commit_pulls_url = '/repos/sanitizers/chronographer/commits/f2114ef/pulls'
    gh_api = make_gh_api({commit_pulls_url: [PULL_REQUEST_PAYLOAD]})
    event = make_event(
        'check_suite',
        {'check_suite': {'head_sha': 'f2114ef', 'pull_requests': []}},
    )

    pull_request = asyncio.run(
        resolve_pull_request(event, 'sanitizers/chronographer', gh_api),
    )

    assert pull_request is PULL_REQUEST_PAYLOAD
    assert gh_api.requested_urls == [commit_pulls_url]


def test_check_without_any_pull_request_is_skipped(make_gh_api):
    """Check that a branch-only check run resolves to nothing."""
    commit_pulls_url = '/repos/sanitizers/chronographer/commits/f2114ef/pulls'
    gh_api = make_gh_api({commit_pulls_url: []})
    event = make_event(
        'check_suite',
        {'check_suite': {'head_sha': 'f2114ef', 'pull_requests': []}},
    )

    assert asyncio.run(
        resolve_pull_request(event, 'sanitizers/chronographer', gh_api),
    ) is None


def test_pull_request_event_needs_no_api_call(make_gh_api):
    """Check that ``pull_request`` payloads are used as they arrive."""
    gh_api = make_gh_api()
    event = make_event('pull_request', {'pull_request': PULL_REQUEST_PAYLOAD})

    pull_request = asyncio.run(
        resolve_pull_request(event, 'sanitizers/chronographer', gh_api),
    )

    assert pull_request is PULL_REQUEST_PAYLOAD
    assert not gh_api.requested_urls


@pytest.mark.parametrize(
    ('towncrier_config', 'expected'),
    [
        ({}, 'news'),
        ({'directory': 'changelog.d/'}, 'changelog.d'),
        ({'directory': ''}, 'news'),
    ],
)
def test_change_note_base_dir(towncrier_config, expected):
    """Check where the change notes are looked for."""
    assert change_note_base_dir(towncrier_config) == expected


def test_change_note_types_keeps_the_configured_order():
    """Check that the types come back as towncrier lists them."""
    assert change_note_types(
        {'type': [{'directory': 'feature'}, {'directory': 'bugfix'}]},
    ) == ('feature', 'bugfix')


def test_change_note_types_falls_back_to_the_defaults():
    """Check that a config without types still yields some."""
    assert 'bugfix' in change_note_types({})


@pytest.mark.parametrize('key', ['enforce-name', 'enforce_name'])
def test_enforce_name_settings_accepts_both_spellings(key):
    """Check that the legacy underscore spelling still resolves."""
    assert enforce_name_settings({key: {'suffix': '.rst'}}) == {
        'suffix': '.rst',
    }


def test_enforce_name_settings_defaults_to_empty():
    """Check that an absent section does not blow up the callers."""
    assert enforce_name_settings({}) == {}


def test_actions_lead_with_the_types_the_labels_demand():
    """Check that a demanded type outranks the rest of the config."""
    actions = build_change_note_actions(
        demanded_types=['feature'],
        known_types=('bugfix', 'doc', 'feature', 'misc'),
    )

    assert [action['label'] for action in actions] == [
        'feature', 'bugfix', 'doc',
    ]


def test_actions_drop_types_towncrier_does_not_know():
    """Check that a misconfigured demand does not reach the buttons."""
    actions = build_change_note_actions(
        demanded_types=['typo'],
        known_types=('bugfix',),
    )

    assert [action['label'] for action in actions] == ['bugfix']


def test_actions_drop_types_too_long_to_identify():
    """Check that the 20-character identifier cap is respected."""
    actions = build_change_note_actions(
        demanded_types=[],
        known_types=('backwards-incompatible', 'bugfix'),
    )

    assert [action['label'] for action in actions] == ['bugfix']


def test_actions_fit_what_the_checks_api_accepts():
    """Check that the rendered actions survive the API model."""
    actions = build_change_note_actions(
        demanded_types=[],
        known_types=('bugfix', 'doc', 'feature', 'misc', 'removal'),
    )

    assert len(actions) == 3
    assert UpdateCheckRequest(name='Timeline protection', actions=actions)


def test_actions_identify_the_type_they_create():
    """Check that a click tells the handler which note to write."""
    actions = build_change_note_actions(
        demanded_types=['bugfix'],
        known_types=('bugfix',),
    )

    assert actions[0]['identifier'] == 'mkfrag:bugfix'


HEAD_REPO_SLUG = 'contributor/chronographer'


def make_check_run_event(identifier):
    """Build a ``requested_action`` payload pointing at a fork branch."""
    return make_event(
        'check_run',
        {
            'check_run': {
                'check_suite': {
                    'head_sha': 'f2114ef',
                    'pull_requests': [],
                },
                'id': 42,
                'name': 'Timeline protection',
            },
            'repository': {
                'default_branch': 'devel',
                'full_name': 'sanitizers/chronographer',
            },
            'requested_action': {'identifier': identifier},
        },
    )


# Every keyword here names one independent thing the handler reads out
# of its surroundings, so bundling them would only add indirection:
# pylint: disable-next=too-many-arguments
def run_change_note_request(
        monkeypatch, identifier, *, gh_api=None, head_repo=True,
        repo_config=None, towncrier_config=None,
):
    """Drive the button handler against a fake GitHub API."""
    gh_api = gh_api if gh_api is not None else FakeGitHubAPI()
    gh_api.responses.setdefault(
        '/repos/sanitizers/chronographer/commits/f2114ef/pulls',
        [
            {
                'head': {
                    'ref': 'add-a-thing',
                    'repo':
                        {'full_name': HEAD_REPO_SLUG} if head_repo else None,
                    'sha': 'f2114ef',
                },
                'number': 7,
                'title': 'Add a thing',
            },
        ],
    )

    async def fake_chronographer_config(**_kwargs):
        return repo_config if repo_config is not None else {}

    async def fake_towncrier_config(**_kwargs):
        return towncrier_config

    monkeypatch.setattr(
        event_handlers, 'RUNTIME_CONTEXT',
        SimpleNamespace(app_installation_client=gh_api),
    )
    monkeypatch.setattr(
        event_handlers, 'get_chronographer_config', fake_chronographer_config,
    )
    monkeypatch.setattr(
        event_handlers, 'get_towncrier_config', fake_towncrier_config,
    )

    asyncio.run(
        event_handlers.on_change_note_requested(
            make_check_run_event(identifier),
        ),
    )
    return gh_api


def test_requested_note_lands_on_the_head_branch(monkeypatch):
    """Check that a click commits the fragment to the contributor's fork."""
    gh_api = run_change_note_request(monkeypatch, 'mkfrag:bugfix')

    url, data = gh_api.put_calls[0]
    assert len(gh_api.put_calls) == 1
    assert url == f'/repos/{HEAD_REPO_SLUG}/contents/news/7.bugfix'
    assert data['branch'] == 'add-a-thing'
    assert base64.b64decode(data['content']).decode() == 'Add a thing\n'
    assert not gh_api.patch_calls


def test_requested_note_honours_the_configured_layout(monkeypatch):
    """Check that the directory and suffix settings shape the path."""
    gh_api = run_change_note_request(
        monkeypatch,
        'mkfrag:feature',
        repo_config={'enforce-name': {'suffix': '.rst'}},
        towncrier_config={
            'directory': 'changelog.d/',
            'type': [{'directory': 'feature'}],
        },
    )

    url, _data = gh_api.put_calls[0]
    assert url == (
        f'/repos/{HEAD_REPO_SLUG}/contents/changelog.d/7.feature.rst'
    )


def test_unrelated_requested_actions_are_ignored(monkeypatch):
    """Check that another app's button does not write anything."""
    gh_api = run_change_note_request(monkeypatch, 'rerun-everything')

    assert not gh_api.put_calls
    assert not gh_api.requested_urls


def test_unknown_change_types_are_refused(monkeypatch):
    """Check that only a type towncrier accepts gets written."""
    gh_api = run_change_note_request(
        monkeypatch,
        'mkfrag:bugfix',
        towncrier_config={'type': [{'directory': 'feature'}]},
    )

    assert not gh_api.put_calls


def test_a_gone_fork_is_reported_on_the_check_run(monkeypatch):
    """Check that a deleted head repository explains itself."""
    gh_api = run_change_note_request(
        monkeypatch, 'mkfrag:bugfix', head_repo=False,
    )

    assert not gh_api.put_calls
    url, data = gh_api.patch_calls[0]
    assert url == '/repos/sanitizers/chronographer/check-runs/42'
    assert data['conclusion'] == 'failure'
    assert 'gone' in data['output']['summary']


def test_a_rejected_push_is_reported_on_the_check_run(monkeypatch):
    """Check that a write the app may not make is not silent."""
    gh_api = run_change_note_request(
        monkeypatch,
        'mkfrag:bugfix',
        gh_api=FakeGitHubAPI(
            put_error=gidgethub.BadRequest(HTTPStatus.FORBIDDEN),
        ),
    )

    url, data = gh_api.patch_calls[0]
    assert url == '/repos/sanitizers/chronographer/check-runs/42'
    assert data['conclusion'] == 'failure'
    assert 'news/7.bugfix' in data['output']['summary']


@pytest.mark.parametrize(
    ('pr_body', 'expected'),
    [
        ('Closes #12', [12]),
        ('fixes GH-7', [7]),
        ('Resolved: #3', [3]),
        (
            'Fixes https://github.com/sanitizers/chronographer/issues/42',
            [42],
        ),
        ('Closes sanitizers/chronographer#5', [5]),
        ('Closes someone/else#5', []),
        (
            'Fixes https://github.com/someone/else/issues/42',
            [],
        ),
        ('Related to #9', []),
        ('Closes #4 and closes #4', [4]),
        ('Closes #4, fixes #2', [2, 4]),
        (None, []),
        ('', []),
    ],
)
def test_linked_issue_numbers(pr_body, expected):
    """Check which issue references count as closing this PR."""
    assert find_linked_issue_numbers(
        pr_body, 'sanitizers/chronographer',
    ) == expected


def collect_labels(gh_api, *, labels, body='', requirements=None):
    """Drive the label collection against a fake GitHub API."""
    return asyncio.run(
        collect_requirement_labels(
            gh_api,
            repo_slug='sanitizers/chronographer',
            pull_request={
                'labels': [{'name': name} for name in labels],
                'body': body,
            },
            requirements=(
                requirements if requirements is not None
                else {'enhancement': ['feature'], 'bug': ['bugfix']}
            ),
        ),
    )


def test_own_voting_label_silences_the_linked_issues(make_gh_api):
    """Check that a PR carrying a voting label speaks for itself."""
    gh_api = make_gh_api()

    label_origins = collect_labels(
        gh_api, labels=['enhancement'], body='Closes #12',
    )

    assert label_origins == {'enhancement': None}
    assert not gh_api.requested_urls


def test_labels_are_inherited_from_the_linked_issues(make_gh_api):
    """Check that a PR with no voting label borrows the issue's."""
    issue_url = '/repos/sanitizers/chronographer/issues/12'
    gh_api = make_gh_api({issue_url: {'labels': [{'name': 'enhancement'}]}})

    label_origins = collect_labels(
        gh_api, labels=['needs-review'], body='Closes #12',
    )

    assert label_origins == {'needs-review': None, 'enhancement': 12}
    assert gh_api.requested_urls == [issue_url]


def test_own_labels_outrank_the_inherited_ones(make_gh_api):
    """Check that a label held by both sides stays the PR's own.

    ``needs-review`` is not a voting label, so the lookup still
    happens -- but its origin must not become the linked issue.
    """
    issue_url = '/repos/sanitizers/chronographer/issues/12'
    gh_api = make_gh_api({issue_url: {'labels': [{'name': 'needs-review'}]}})

    assert collect_labels(
        gh_api, labels=['needs-review'], body='Closes #12',
    ) == {'needs-review': None}


def test_an_unreachable_linked_issue_is_ignored(make_gh_api):
    """Check that a dead reference does not sink the whole check run."""
    gh_api = make_gh_api({
        '/repos/sanitizers/chronographer/issues/12':
            gidgethub.BadRequest(status_code=HTTPStatus.NOT_FOUND),
        '/repos/sanitizers/chronographer/issues/13':
            {'labels': [{'name': 'bug'}]},
    })

    assert collect_labels(
        gh_api, labels=[], body='Closes #12, fixes #13',
    ) == {'bug': 13}


def test_check_result_names_the_issue_a_demand_came_from():
    """Check that an inherited demand says which issue asked for it."""
    _conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='',
        fragments_added=['news/123.bugfix'],
        fragments_required=True,
        fragment_re='<re>',
        unmet_change_type_requirements={'enhancement': ['feature']},
        label_origins={'enhancement': 12},
    )

    assert '`enhancement` (from #12) wants' in output['summary']


def test_check_result_stays_quiet_about_the_pull_requests_own_labels():
    """Check that a label the PR carries itself gets no provenance."""
    _conclusion, output = build_check_result(
        title_prefix='chng: ',
        epilogue='',
        fragments_added=['news/123.bugfix'],
        fragments_required=True,
        fragment_re='<re>',
        unmet_change_type_requirements={'enhancement': ['feature']},
        label_origins={'enhancement': None},
    )

    assert '`enhancement` wants' in output['summary']
