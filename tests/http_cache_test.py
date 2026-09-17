"""Tests for the conditional GitHub API response cache."""

import asyncio
import json

import pytest
from gidgethub.abc import GitHubAPI

from chronographer.http_cache import (
    DEFAULT_MAX_ENTRIES,
    MAX_ENTRIES_ENV_VAR,
    LRUCache,
    cache_gh_api_gets,
    make_cache,
)


class ReplayGitHubAPI(GitHubAPI):
    """Serve canned HTTP responses, recording the request headers."""

    def __init__(self, responses):
        """Queue up the responses to serve, oldest first."""
        super().__init__('test')
        self.responses = list(responses)
        self.sent_headers = []

    async def _request(self, method, url, headers, body=b''):
        """Pop the next canned response off the queue."""
        self.sent_headers.append(headers)
        return self.responses.pop(0)

    async def sleep(self, seconds):
        """Pretend to have slept."""


def _json_response(payload, *, etag):
    """Build a 200 response carrying ``payload`` and an ``ETag``."""
    return (
        200,
        {
            'content-type': 'application/json; charset=utf-8',
            'etag': etag,
        },
        json.dumps(payload).encode(),
    )


NOT_MODIFIED_RESPONSE = (304, {'content-type': 'application/json'}, b'')


def test_lru_cache_evicts_the_oldest_entry():
    """Check that a full cache drops what was stored first."""
    cache = LRUCache(2)
    cache['first'] = 1
    cache['second'] = 2
    cache['third'] = 3

    assert list(cache) == ['second', 'third']


def test_lru_cache_reading_an_entry_keeps_it():
    """Check that a read entry outlives an older unread one."""
    cache = LRUCache(2)
    cache['first'] = 1
    cache['second'] = 2

    assert cache['first'] == 1

    cache['third'] = 3

    assert list(cache) == ['first', 'third']


def test_lru_cache_signals_a_miss_with_a_key_error():
    """Check the lookup protocol GidgetHub relies on."""
    with pytest.raises(KeyError):
        LRUCache(2)['missing']  # pylint: disable=expression-not-assigned


def test_missing_env_var_yields_the_default_size(monkeypatch):
    """Check that the cache is on with nothing configured."""
    monkeypatch.delenv(MAX_ENTRIES_ENV_VAR, raising=False)

    assert make_cache().max_entries == DEFAULT_MAX_ENTRIES


def test_a_zero_sized_cache_is_no_cache(monkeypatch):
    """Check that the env var can turn the caching off."""
    monkeypatch.setenv(MAX_ENTRIES_ENV_VAR, '0')

    assert make_cache() is None


def test_a_bogus_env_var_falls_back_to_the_default(monkeypatch):
    """Check that a typo does not take the app down."""
    monkeypatch.setenv(MAX_ENTRIES_ENV_VAR, 'many')

    assert make_cache().max_entries == DEFAULT_MAX_ENTRIES


def test_a_sized_env_var_is_honored(monkeypatch):
    """Check that the configured size reaches the cache."""
    monkeypatch.setenv(MAX_ENTRIES_ENV_VAR, ' 7 ')

    assert make_cache().max_entries == 7


def test_a_repeated_get_is_revalidated(monkeypatch):
    """Check that a 304 replays the payload seen the first time."""
    monkeypatch.setattr(
        'chronographer.http_cache.GITHUB_API_CACHE',
        LRUCache(DEFAULT_MAX_ENTRIES),
    )
    gh_api = cache_gh_api_gets(
        ReplayGitHubAPI([
            _json_response({'content': 'aGk='}, etag='"v1"'),
            NOT_MODIFIED_RESPONSE,
        ]),
    )

    url = '/repos/org/repo/contents/.github/cfg.yml'
    first = asyncio.run(gh_api.getitem(url))
    second = asyncio.run(gh_api.getitem(url))

    assert first == second == {'content': 'aGk='}
    assert 'if-none-match' not in gh_api.sent_headers[0]
    assert gh_api.sent_headers[1]['if-none-match'] == '"v1"'


def test_the_cache_outlives_a_single_api_client(monkeypatch):
    """Check that the next event revalidates what this one stored."""
    monkeypatch.setattr(
        'chronographer.http_cache.GITHUB_API_CACHE',
        LRUCache(DEFAULT_MAX_ENTRIES),
    )
    url = 'https://github.com/org/repo/pull/1.diff'
    first_client = cache_gh_api_gets(
        ReplayGitHubAPI([_json_response(['a diff'], etag='"v1"')]),
    )
    asyncio.run(first_client.getitem(url))

    next_client = cache_gh_api_gets(
        ReplayGitHubAPI([NOT_MODIFIED_RESPONSE]),
    )

    assert asyncio.run(next_client.getitem(url)) == ['a diff']
    assert next_client.sent_headers[0]['if-none-match'] == '"v1"'


def test_a_disabled_cache_leaves_the_client_alone(monkeypatch):
    """Check that no conditional headers are sent when off."""
    monkeypatch.setattr('chronographer.http_cache.GITHUB_API_CACHE', None)
    gh_api = cache_gh_api_gets(
        ReplayGitHubAPI([
            _json_response({'a': 1}, etag='"v1"'),
            _json_response({'a': 2}, etag='"v2"'),
        ]),
    )

    assert asyncio.run(gh_api.getitem('/rate_limit')) == {'a': 1}
    assert asyncio.run(gh_api.getitem('/rate_limit')) == {'a': 2}
    assert 'if-none-match' not in gh_api.sent_headers[1]
