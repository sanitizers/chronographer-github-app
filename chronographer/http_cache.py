"""A process-wide cache of conditional GitHub API GET responses."""

import collections
import logging
import os
import typing


logger = logging.getLogger(__name__)


DEFAULT_MAX_ENTRIES = 128
"""How many GET responses to keep around unless configured otherwise."""

MAX_ENTRIES_ENV_VAR = 'CHRONOGRAPHER_HTTP_CACHE_ENTRIES'
"""Env var setting the cache size. ``0`` turns the caching off."""


class LRUCache(collections.OrderedDict):
    """A mapping evicting the least recently used entry when full."""

    def __init__(self, max_entries: int) -> None:
        """Remember how many entries may be retained."""
        super().__init__()
        self.max_entries = max_entries

    def __getitem__(self, key: str) -> typing.Any:
        """Return the entry stored under ``key``, marking it fresh."""
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key: str, value: typing.Any) -> None:
        """Store ``value`` under ``key``, evicting stale entries."""
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_entries:
            self.popitem(last=False)


def make_cache() -> typing.Optional[LRUCache]:
    """Build the shared cache as configured in the environment."""
    configured_max_entries = os.environ.get(MAX_ENTRIES_ENV_VAR, '').strip()
    if not configured_max_entries:
        return LRUCache(DEFAULT_MAX_ENTRIES)

    try:
        max_entries = int(configured_max_entries)
    except ValueError:
        logger.warning(
            '`%s` is set to `%s` which is not a number. '
            'Falling back to caching %d responses.',
            MAX_ENTRIES_ENV_VAR,
            configured_max_entries,
            DEFAULT_MAX_ENTRIES,
        )
        return LRUCache(DEFAULT_MAX_ENTRIES)

    if max_entries <= 0:
        logger.info(
            '`%s` is set to %d so the GitHub API responses '
            'will not be cached.',
            MAX_ENTRIES_ENV_VAR,
            max_entries,
        )
        return None

    return LRUCache(max_entries)


GITHUB_API_CACHE = make_cache()
"""The cache shared by every webhook event this process handles."""


def cache_gh_api_gets(gh_api):
    """Let ``gh_api`` revalidate its GET responses against the cache.

    GidgetHub accepts such a cache as a constructor argument but
    Octomachinery builds a brand new API client on every attribute
    access, dropping whatever it accumulated with the previous one.
    Attaching the process-wide cache to the client that the current
    event got is what makes the entries outlive a single event.

    The cached entries are only ever used to make a conditional
    request -- GitHub decides whether they are still current, so
    nothing here can go stale. Sharing them between the installations
    this process serves is just as safe: an entry is keyed by the URL
    it came from, every request still carries its own installation
    token, and GitHub only answers `304` to a caller it would have
    served the very same contents anyway.
    """
    if GITHUB_API_CACHE is not None:
        # pylint: disable=protected-access
        gh_api._cache = GITHUB_API_CACHE
    return gh_api
