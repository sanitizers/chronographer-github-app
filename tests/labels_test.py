"""Tests for the change note label lifecycle."""

import asyncio

import pytest

from chronographer.labels import (
    apply_label_changes,
    head_moved_since_label,
    label_applied_at,
    LABEL_MORE,
    LABEL_PROVIDED,
    LABEL_REQUIRED,
    LABEL_SKIP,
    plan_label_changes,
    resolve_label_names,
)


DEFAULT_NAMES = {
    'skip': LABEL_SKIP,
    'provided': LABEL_PROVIDED,
    'required': LABEL_REQUIRED,
    'more': LABEL_MORE,
}


def test_label_names_fall_back_to_the_defaults():
    """Check that an empty config still names all four labels."""
    assert resolve_label_names({}) == DEFAULT_NAMES


def test_label_names_are_configurable():
    """Check that the config renames labels and switches them off."""
    names = resolve_label_names({
        'labels': {'fragment-provided': 'noted', 'fragment-required': None},
    })

    assert names['provided'] == 'noted'
    assert names['required'] is None
    assert names['skip'] == LABEL_SKIP


@pytest.mark.parametrize(
    ('conclusion', 'current', 'add', 'remove'),
    [
        ('success', set(), [LABEL_PROVIDED], []),
        ('success', {LABEL_REQUIRED}, [LABEL_PROVIDED], [LABEL_REQUIRED]),
        ('failure', set(), [LABEL_REQUIRED], []),
        ('failure', {LABEL_PROVIDED}, [LABEL_REQUIRED], [LABEL_PROVIDED]),
        ('action_required', set(), [LABEL_PROVIDED], []),
        (
            'neutral', {LABEL_PROVIDED, LABEL_REQUIRED}, [],
            [LABEL_PROVIDED, LABEL_REQUIRED],
        ),
        ('success', {LABEL_PROVIDED}, [], []),
    ],
)
def test_label_plan_follows_the_conclusion(conclusion, current, add, remove):
    """Check which labels each check run verdict asks for."""
    assert plan_label_changes(
        conclusion=conclusion,
        current_labels=current,
        names=DEFAULT_NAMES,
    ) == (add, remove)


def test_a_disabled_label_is_never_requested():
    """Check that a ``~`` in the config keeps the label out of the plan."""
    names = dict(DEFAULT_NAMES, provided=None)

    assert plan_label_changes(
        conclusion='success',
        current_labels={LABEL_REQUIRED},
        names=names,
    ) == ([], [LABEL_REQUIRED])


def test_the_more_label_is_only_dropped_when_asked():
    """Check that ``more`` survives a verdict on its own."""
    assert plan_label_changes(
        conclusion='action_required',
        current_labels={LABEL_MORE, LABEL_PROVIDED},
        names=DEFAULT_NAMES,
    ) == ([], [])

    assert plan_label_changes(
        conclusion='success',
        current_labels={LABEL_MORE, LABEL_PROVIDED},
        names=DEFAULT_NAMES,
        drop_more=True,
    ) == ([], [LABEL_MORE])


def test_applying_changes_posts_once_and_deletes_each(make_gh_api):
    """Check that the Issues API is asked for the planned changes only."""
    gh_api = make_gh_api()

    asyncio.run(
        apply_label_changes(
            gh_api,
            issue_url='/repos/o/r/issues/1',
            add=[LABEL_PROVIDED],
            remove=[LABEL_REQUIRED, 'needs work'],
        ),
    )

    assert gh_api.post_calls == [
        ('/repos/o/r/issues/1/labels', {'labels': [LABEL_PROVIDED]}),
    ]
    assert gh_api.delete_calls == [
        f'/repos/o/r/issues/1/labels/{LABEL_REQUIRED}'.replace(':', '%3A'),
        '/repos/o/r/issues/1/labels/needs%20work',
    ]


def test_an_empty_plan_makes_no_requests(make_gh_api):
    """Check that nothing to do means no API traffic."""
    gh_api = make_gh_api()

    asyncio.run(
        apply_label_changes(
            gh_api, issue_url='/repos/o/r/issues/1', add=[], remove=[],
        ),
    )

    assert gh_api.post_calls == []
    assert gh_api.delete_calls == []


def make_issue_events(*events):
    """Build the issue event list the timeline lookup walks."""
    return [
        {'event': action, 'label': {'name': label}, 'created_at': created_at}
        for action, label, created_at in events
    ]


def test_relabeling_reports_the_latest_application(make_gh_api):
    """Check that a label taken off and put back on reports the last time."""
    gh_api = make_gh_api({
        '/repos/o/r/issues/1/events': make_issue_events(
            ('labeled', LABEL_MORE, '2020-01-01T00:00:00Z'),
            ('unlabeled', LABEL_MORE, '2020-01-02T00:00:00Z'),
            ('labeled', LABEL_MORE, '2020-01-03T00:00:00Z'),
        ),
    })

    assert asyncio.run(
        label_applied_at(
            gh_api, issue_url='/repos/o/r/issues/1', label=LABEL_MORE,
        ),
    ) == '2020-01-03T00:00:00Z'


def test_a_removed_label_reports_no_application(make_gh_api):
    """Check that an unlabeling clears the recorded timestamp."""
    gh_api = make_gh_api({
        '/repos/o/r/issues/1/events': make_issue_events(
            ('labeled', LABEL_MORE, '2020-01-01T00:00:00Z'),
            ('unlabeled', LABEL_MORE, '2020-01-02T00:00:00Z'),
        ),
    })

    assert asyncio.run(
        label_applied_at(
            gh_api, issue_url='/repos/o/r/issues/1', label=LABEL_MORE,
        ),
    ) is None


def check_head_moved(make_gh_api, *, labeled_at, committed_at):
    """Compare a labeling against the head commit of a pull request."""
    gh_api = make_gh_api({
        '/repos/o/r/issues/1/events': (
            [] if labeled_at is None
            else make_issue_events(('labeled', LABEL_MORE, labeled_at))
        ),
        '/repos/o/r/commits/deadbeef': {
            'commit': {'committer': {'date': committed_at}},
        },
    })
    return asyncio.run(
        head_moved_since_label(
            gh_api,
            repo_slug='o/r',
            issue_url='/repos/o/r/issues/1',
            head_sha='deadbeef',
            label=LABEL_MORE,
        ),
    )


def test_a_push_after_the_label_answers_it(make_gh_api):
    """Check that a newer head commit counts as an answer."""
    assert check_head_moved(
        make_gh_api,
        labeled_at='2020-01-01T00:00:00Z',
        committed_at='2020-01-02T00:00:00Z',
    )


def test_a_push_before_the_label_does_not_answer_it(make_gh_api):
    """Check that the demand outlives the commit it was made about."""
    assert not check_head_moved(
        make_gh_api,
        labeled_at='2020-01-02T00:00:00Z',
        committed_at='2020-01-01T00:00:00Z',
    )


def test_an_unaccounted_label_is_treated_as_unanswered(make_gh_api):
    """Check that a missing labeling event keeps the demand standing."""
    assert not check_head_moved(
        make_gh_api, labeled_at=None, committed_at='2020-01-02T00:00:00Z',
    )
