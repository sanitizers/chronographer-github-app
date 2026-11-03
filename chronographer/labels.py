"""GitHub label management helpers."""
from datetime import datetime
import logging
from urllib.parse import quote


logger = logging.getLogger(__name__)


LABEL_SKIP = 'bot:chronographer:skip'
"""GitHub label meaning that the change fragment is not needed."""
LABEL_REQUIRED = 'bot:chronographer:required'
"""GitHub label meaning that the change fragment is needed."""
LABEL_PROVIDED = 'bot:chronographer:provided'
"""GitHub label meaning that the change fragment is in place."""
LABEL_MORE = 'bot:chronographer:more'
"""GitHub label meaning that the change fragment needs updating."""


# The repository config key each label name is read from, and the
# default it falls back to.  Mapping a key to ``~`` turns that label
# off entirely:
LABEL_CONFIG_DEFAULTS = {
    'skip': ('skip-changelog', LABEL_SKIP),
    'provided': ('fragment-provided', LABEL_PROVIDED),
    'required': ('fragment-required', LABEL_REQUIRED),
    'more': ('fragment-more', LABEL_MORE),
}

# The check run conclusions that mean a change note is in place, and the
# ones that mean the pull request still owes one:
CONCLUSIONS_WITH_CHANGE_NOTE = frozenset({'success', 'action_required'})
CONCLUSIONS_WITHOUT_CHANGE_NOTE = frozenset({'failure'})


def resolve_label_names(repo_config):
    """Read the four label names the repository config settles on."""
    labels_config = repo_config.get('labels') or {}
    return {
        role: labels_config.get(config_key, default)
        for role, (config_key, default) in LABEL_CONFIG_DEFAULTS.items()
    }


def plan_label_changes(*, conclusion, current_labels, names, drop_more=False):
    """Work out which of the bot's own labels need adding or removing.

    The verdict the check run reached is the only input that matters:
    a change note is either in place (``provided``) or still owed
    (``required``), and a pull request that needs no change note at all
    carries neither.  Labels switched off in the config -- and the ones
    already in the wanted state -- produce no request.
    """
    wanted = set()
    unwanted = set()
    if conclusion in CONCLUSIONS_WITH_CHANGE_NOTE:
        wanted.add(names['provided'])
        unwanted.add(names['required'])
    elif conclusion in CONCLUSIONS_WITHOUT_CHANGE_NOTE:
        wanted.add(names['required'])
        unwanted.add(names['provided'])
    else:
        unwanted.update({names['provided'], names['required']})

    if drop_more:
        unwanted.add(names['more'])

    return (
        sorted((wanted - {None}) - set(current_labels)),
        sorted((unwanted - {None}) & set(current_labels)),
    )


async def apply_label_changes(gh_api, *, issue_url, add, remove):
    """Put the planned label changes through the Issues API."""
    if add:
        logger.info('Labeling %s with %s', issue_url, ', '.join(add))
        await gh_api.post(
            f'{issue_url!s}/labels',
            preview_api_version='symmetra',
            data={'labels': list(add)},
        )

    for label in remove:
        logger.info('Removing the %s label from %s', label, issue_url)
        await gh_api.delete(
            f'{issue_url!s}/labels/{quote(label)!s}',
            preview_api_version='symmetra',
        )


async def label_applied_at(gh_api, *, issue_url, label):
    """Return when a label was last put on an issue, if it still is.

    The issue events are replayed in order so that a label taken off and
    put back on reports the latest of the two.
    """
    applied_at = None
    async for issue_event in gh_api.getiter(f'{issue_url!s}/events'):
        if (issue_event.get('label') or {}).get('name') != label:
            continue
        if issue_event['event'] == 'labeled':
            applied_at = issue_event['created_at']
        elif issue_event['event'] == 'unlabeled':
            applied_at = None
    return applied_at


async def head_moved_since_label(
    gh_api, *, repo_slug, issue_url, head_sha,
    label,
):
    """Tell whether the head branch was pushed to after the labeling.

    This is the only evidence GitHub offers that a contributor answered
    a maintainer asking for more: nothing records how much more was
    wanted, so a push after the request counts as the answer.  A label
    the issue events do not account for is treated as unanswered.
    """
    applied_at = await label_applied_at(
        gh_api, issue_url=issue_url, label=label,
    )
    if applied_at is None:
        return False

    head_commit = await gh_api.getitem(
        f'/repos/{repo_slug!s}/commits/{head_sha!s}',
    )
    return (
        _parse_timestamp(head_commit['commit']['committer']['date'])
        > _parse_timestamp(applied_at)
    )


def _parse_timestamp(iso_8601):
    """Turn a GitHub timestamp into a comparable datetime."""
    return datetime.fromisoformat(iso_8601.replace('Z', '+00:00'))
