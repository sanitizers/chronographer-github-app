"""Tests for the change note helpers."""

import pytest

from chronographer.change_notes import (
    change_note_base_dir,
    change_note_types,
    collect_change_notes,
    contentless_change_types,
    enforce_name_settings,
    is_a_release_pr,
    requires_changelog,
)

from .conftest import (
    ADDED_FRAGMENT_DIFF,
    CHANGELOG_ADDITION_DIFF,
    CONTENTLESS_TOWNCRIER_CONFIG,
    EMPTY_CONTENTLESS_FRAGMENT_DIFF,
    FILLED_CONTENTLESS_FRAGMENT_DIFF,
    make_fragment_re,
    MODIFIED_FRAGMENT_DIFF,
    REMOVED_FRAGMENT_DIFF,
    SOURCE_CHANGE_DIFF,
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


def test_added_fragment_is_detected(make_diff):
    """Check that a new fragment file is recognised in a diff."""
    fragment_re = make_fragment_re()
    diff = make_diff(ADDED_FRAGMENT_DIFF + SOURCE_CHANGE_DIFF)

    assert [
        patched_file.path for patched_file in diff
        if patched_file.is_added_file and fragment_re.search(patched_file.path)
    ] == ['news/123.bugfix']


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


def test_contentless_change_types_lists_hidden_bodies():
    """Report the types towncrier renders without their contents."""
    assert contentless_change_types(CONTENTLESS_TOWNCRIER_CONFIG) == {
        'trivial',
    }


def test_contentless_change_types_defaults_to_showing():
    """Treat a type without ``showcontent`` as rendering its body."""
    assert not contentless_change_types({'type': [{'directory': 'misc'}]})


@pytest.mark.parametrize(
    ('diff_text', 'expected'),
    [
        (ADDED_FRAGMENT_DIFF, True),
        (MODIFIED_FRAGMENT_DIFF, True),
        (REMOVED_FRAGMENT_DIFF, False),
        (SOURCE_CHANGE_DIFF, False),
    ],
)
def test_collect_change_notes_accepts_touched_fragments(
        make_diff, diff_text, expected,
):
    """Count both new and edited change notes, but not deleted ones."""
    accepted, overfull = collect_change_notes(
        make_diff(diff_text), make_fragment_re(),
    )

    assert bool(accepted) is expected
    assert not overfull


def test_collect_change_notes_accepts_empty_contentless_note(make_diff):
    """Let a ``showcontent = false`` note through while it is empty."""
    fragment_re = make_fragment_re(
        towncrier_config=CONTENTLESS_TOWNCRIER_CONFIG,
    )

    accepted, overfull = collect_change_notes(
        make_diff(EMPTY_CONTENTLESS_FRAGMENT_DIFF),
        fragment_re,
        contentless_change_types(CONTENTLESS_TOWNCRIER_CONFIG),
    )

    assert [note.path for note in accepted] == ['news/123.trivial']
    assert not overfull


def test_collect_change_notes_flags_filled_contentless_note(make_diff):
    """Single out a ``showcontent = false`` note carrying text."""
    fragment_re = make_fragment_re(
        towncrier_config=CONTENTLESS_TOWNCRIER_CONFIG,
    )

    accepted, overfull = collect_change_notes(
        make_diff(FILLED_CONTENTLESS_FRAGMENT_DIFF),
        fragment_re,
        contentless_change_types(CONTENTLESS_TOWNCRIER_CONFIG),
    )

    assert not accepted
    assert [note.path for note in overfull] == ['news/123.trivial']


def test_collect_change_notes_keeps_filled_note_of_rendered_type(make_diff):
    """Accept text in a type whose body does reach the changelog."""
    accepted, overfull = collect_change_notes(
        make_diff(ADDED_FRAGMENT_DIFF),
        make_fragment_re(towncrier_config=CONTENTLESS_TOWNCRIER_CONFIG),
        contentless_change_types(CONTENTLESS_TOWNCRIER_CONFIG),
    )

    assert [note.path for note in accepted] == ['news/123.bugfix']
    assert not overfull
