"""Tests for the helpers backing the webhook event handlers."""

import asyncio

import pytest

from chronographer.event_handlers import (
    build_check_result,
    compile_towncrier_fragments_regex,
    is_a_release_pr,
    is_blacklisted,
    is_org_allowed,
    requires_changelog,
    resolve_pull_request,
)

from .conftest import (
    ADDED_FRAGMENT_DIFF,
    CHANGELOG_ADDITION_DIFF,
    make_event,
    make_pull_request_event,
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
    ('allowlist', 'owner_login', 'expected'),
    [
        (None, 'acme', True),
        ('', 'acme', True),
        ('   ', 'acme', True),
        ('psf', 'psf', True),
        ('psf', 'acme', False),
        ('psf,aio-libs', 'aio-libs', True),
        ('psf, aio-libs', 'aio-libs', True),
        ('psf\naio-libs', 'aio-libs', True),
        ('psf', 'PSF', True),
        ('PSF', 'psf', True),
        ('psf', 'psf-releng', False),
        ('webknjaz', 'webknjaz', True),
    ],
)
def test_is_org_allowed(monkeypatch, allowlist, owner_login, expected):
    """Check how the deployment-side allow list is parsed and matched."""
    if allowlist is None:
        monkeypatch.delenv('CHRONOGRAPHER_ALLOWED_ORGS', raising=False)
    else:
        monkeypatch.setenv('CHRONOGRAPHER_ALLOWED_ORGS', allowlist)

    assert is_org_allowed(owner_login) is expected


def test_unserved_account_is_told_so_and_costs_no_diff(monkeypatch, run_on_pr):
    """Check that a PR outside of the allow list stops at one check run."""
    monkeypatch.setenv('CHRONOGRAPHER_ALLOWED_ORGS', 'psf')

    gh_api = run_on_pr(make_pull_request_event(owner_login='acme'))

    assert len(gh_api.posted) == 1
    check_runs_uri, check_run = gh_api.posted[0]
    assert check_runs_uri == '/repos/acme/widget/check-runs'
    assert check_run['status'] == 'completed'
    assert check_run['conclusion'] == 'neutral'
    assert 'acme' in check_run['output']['text']
    assert not gh_api.requested_urls  # the diff was never downloaded
    assert not gh_api.patched  # and the run was never revisited


def test_served_account_is_processed_as_usual(monkeypatch, run_on_pr):
    """Check that an allow-listed account reaches the diff inspection."""
    monkeypatch.setenv('CHRONOGRAPHER_ALLOWED_ORGS', 'acme, psf')
    diff_url = 'https://github.com/acme/widget/pull/7.diff'

    gh_api = run_on_pr(
        make_pull_request_event(owner_login='acme'),
        responses={diff_url: SOURCE_CHANGE_DIFF},
    )

    assert gh_api.posted[0][1]['status'] == 'queued'
    assert diff_url in gh_api.requested_urls


def test_an_empty_allowlist_serves_everyone(monkeypatch, run_on_pr):
    """Check that the default deployment stays open to all accounts."""
    monkeypatch.delenv('CHRONOGRAPHER_ALLOWED_ORGS', raising=False)
    diff_url = 'https://github.com/acme/widget/pull/7.diff'

    gh_api = run_on_pr(
        make_pull_request_event(owner_login='acme'),
        responses={diff_url: SOURCE_CHANGE_DIFF},
    )

    assert gh_api.posted[0][1]['status'] == 'queued'
    assert diff_url in gh_api.requested_urls
