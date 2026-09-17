"""Shared test helpers."""

import asyncio
from io import StringIO
from types import SimpleNamespace

import pytest
from unidiff import PatchSet

from chronographer import event_handlers


@pytest.fixture
def make_diff():
    """Return a factory turning unified diff text into a patch set."""
    return lambda diff_text: PatchSet(StringIO(diff_text))


ADDED_FRAGMENT_DIFF = """\
diff --git a/news/123.bugfix b/news/123.bugfix
new file mode 100644
--- /dev/null
+++ b/news/123.bugfix
@@ -0,0 +1 @@
+Fixed a thing
"""


REMOVED_FRAGMENT_DIFF = """\
diff --git a/news/123.bugfix b/news/123.bugfix
deleted file mode 100644
--- a/news/123.bugfix
+++ /dev/null
@@ -1 +0,0 @@
-Fixed a thing
"""


CHANGELOG_ADDITION_DIFF = """\
diff --git a/NEWS.rst b/NEWS.rst
--- a/NEWS.rst
+++ b/NEWS.rst
@@ -1,2 +1,4 @@
 Changelog
 =========
+
+Fixed a thing
"""


SOURCE_CHANGE_DIFF = """\
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 import os
-x = 1
+x = 2
"""


class FakeGitHubAPI:
    """Record the API calls made and replay canned responses."""

    def __init__(self, responses=None):
        """Store the URL-to-payload mapping to serve."""
        self.responses = responses or {}
        self.requested_urls = []
        self.posted = []
        self.patched = []

    async def getitem(self, url, **_kwargs):
        """Return the canned payload registered for ``url``."""
        self.requested_urls.append(url)
        return self.responses[url]

    async def post(self, url, *, data=None, **_kwargs):
        """Record a POST and reply as the Checks API would."""
        self.posted.append((url, data))
        return {'id': 1, 'check_suite': {'id': 2}}

    async def patch(self, url, *, data=None, **_kwargs):
        """Record a PATCH and reply as the Checks API would."""
        self.patched.append((url, data))
        return {'id': 1, 'check_suite': {'id': 2}}


def make_event(event, data):
    """Stand in for an octomachinery webhook event."""
    return SimpleNamespace(event=event, data=data)


def make_pull_request_event(owner_login='acme', labels=()):
    """Build a minimal ``pull_request`` webhook event."""
    repo_slug = f'{owner_login!s}/widget'
    return make_event(
        'pull_request',
        {
            'repository': {
                'full_name': repo_slug,
                'default_branch': 'main',
                'owner': {'login': owner_login},
            },
            'pull_request': {
                'user': {'login': 'contributor', 'type': 'User'},
                'labels': [{'name': label} for label in labels],
                'number': 7,
                'head': {'ref': 'feature', 'sha': 'deadbeef'},
                'issue_url': f'/repos/{repo_slug!s}/issues/7',
            },
        },
    )


@pytest.fixture
def make_gh_api():
    """Return a factory building a fake GitHub API client."""
    return FakeGitHubAPI


@pytest.fixture
def run_on_pr(monkeypatch):
    """Return a callable driving ``on_pr()`` against a fake GitHub API."""
    def _run(event, responses=None):
        gh_api = FakeGitHubAPI(responses)
        monkeypatch.setattr(
            event_handlers, 'RUNTIME_CONTEXT',
            SimpleNamespace(app_installation_client=gh_api),
        )

        async def _no_repo_config(**_kwargs):
            return {}

        async def _no_towncrier_config(**_kwargs):
            return {}

        monkeypatch.setattr(
            event_handlers, 'get_chronographer_config', _no_repo_config,
        )
        monkeypatch.setattr(
            event_handlers, 'get_towncrier_config', _no_towncrier_config,
        )
        asyncio.run(event_handlers.on_pr(event))
        return gh_api

    return _run
