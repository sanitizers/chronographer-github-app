"""Helpers modelling towncrier change notes in a pull request diff."""

import logging
import re

from .file_utils import get_towncrier_config


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


# The ``.1`` counter towncrier lets a fragment carry between its type and
# its suffix, keyed by what ``enforce-name.number-part`` says about it.
# Forbidding it needs a lookahead rather than an empty string: the
# extra-suffix pattern that follows would otherwise swallow the counter.
COUNTER_PATTERNS = {
    'allow': r'(?:\.\d+)?',
    'require': r'(?:\.\d+)',
    'forbid': r'(?!\.\d+(?:\.|$))',
}
DEFAULT_COUNTER_POLICY = 'allow'


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


def contentless_change_types(towncrier_config):
    """Return the change types towncrier renders without their body."""
    return frozenset(
        change_type['directory']
        for change_type in towncrier_config.get('type', ())
        if not change_type.get('showcontent', True)
    )


def adds_change_note_text(patched_file):
    """Tell whether this diff entry adds any non-blank line."""
    return any(
        line.value.strip()
        for hunk in patched_file
        for line in hunk
        if line.is_added
    )


def collect_change_notes(diff, fragment_re, contentless_types=frozenset()):
    """Split the change notes in a diff into accepted and over-full ones.

    Editing an existing fragment reaches the changelog just like adding
    a new one, so a modified file counts as long as it brings in text.

    A note of a type towncrier is told to render without its body
    (``showcontent = false``) only counts while it stays empty -- any
    text it carries would be dropped from the changelog silently.
    """
    accepted = []
    overfull = []
    for patched_file in diff:
        match = fragment_re.search(patched_file.path)
        if match is None:
            continue

        carries_text = adds_change_note_text(patched_file)
        if not (patched_file.is_added_file or carries_text):
            continue

        is_overfull = carries_text and (
            match.group('fragment_type') in contentless_types
        )
        (overfull if is_overfull else accepted).append(patched_file)

    return accepted, overfull


def enforce_name_settings(repo_config):
    """Return the ``enforce-name`` section, tolerating its old spelling."""
    enforce_name_key = (
        'enforce-name' if 'enforce-name' in repo_config
        else 'enforce_name'
    )
    return repo_config.get(enforce_name_key, {})


def counter_pattern(name_settings):
    """Return the regex chunk covering the fragment counter part.

    An unknown policy is a repository config typo rather than a reason
    to reject every change note, so it degrades to the default.
    """
    policy = name_settings.get('number-part', DEFAULT_COUNTER_POLICY)
    try:
        return COUNTER_PATTERNS[policy]
    except (KeyError, TypeError):
        logger.warning(
            'Ignoring the unknown `enforce-name.number-part` value %r -- '
            'expected one of %s. Falling back to `%s`.',
            policy,
            ', '.join(sorted(COUNTER_PATTERNS)),
            DEFAULT_COUNTER_POLICY,
        )
        return COUNTER_PATTERNS[DEFAULT_COUNTER_POLICY]


def issue_number_pattern(name_settings):
    """Return the regex chunk covering the part before the first dot."""
    return (
        r'(?P<issue_number>\d+)\.'
        if name_settings.get('issue-number', False)
        else r'(?P<issue_number>[^\./]+)\.'
    )


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
            base_dir=re.escape(base_dir),
            file_pattern=issue_number_pattern(name_settings),
            fragment_types=r'|'.join(change_types),
            number_pattern=counter_pattern(name_settings),
            suffix_pattern=r'(\.[^\./]+)*',
            postfix_pattern=fragment_filename_suffix,
        ),
    )


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
