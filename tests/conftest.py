"""Shared test helpers."""

import asyncio
from io import StringIO
from types import SimpleNamespace

import pytest
from unidiff import PatchSet

from chronographer.change_notes import (
    compile_towncrier_fragments_regex,
)


CONTENTLESS_TOWNCRIER_CONFIG = {
    'type': [
        {'directory': 'bugfix', 'showcontent': True},
        {'directory': 'trivial', 'showcontent': False},
    ],
}


def make_fragment_re(name_settings=None, towncrier_config=None):
    """Compile the fragment regex outside of an async context."""
    return asyncio.run(
        compile_towncrier_fragments_regex(
            name_settings=name_settings or {},
            towncrier_config=towncrier_config or {},
        ),
    )


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


SLUG_FRAGMENT_DIFF = """\
diff --git a/news/smth-else.bugfix b/news/smth-else.bugfix
new file mode 100644
--- /dev/null
+++ b/news/smth-else.bugfix
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


MODIFIED_FRAGMENT_DIFF = """\
diff --git a/news/123.bugfix b/news/123.bugfix
--- a/news/123.bugfix
+++ b/news/123.bugfix
@@ -1 +1,2 @@
 Fixed a thing
+and another one
"""


EMPTY_CONTENTLESS_FRAGMENT_DIFF = """\
diff --git a/news/123.trivial b/news/123.trivial
new file mode 100644
--- /dev/null
+++ b/news/123.trivial
"""


FILLED_CONTENTLESS_FRAGMENT_DIFF = """\
diff --git a/news/123.trivial b/news/123.trivial
new file mode 100644
--- /dev/null
+++ b/news/123.trivial
@@ -0,0 +1 @@
+This text never reaches the changelog
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
    """Record the calls made against it and replay canned responses."""

    def __init__(self, responses=None, put_error=None):
        """Store the URL-to-payload mapping to serve."""
        self.responses = responses or {}
        self.put_error = put_error
        self.requested_urls = []
        self.put_calls = []
        self.patch_calls = []

    async def getitem(self, url, **_kwargs):
        """Return the canned payload registered for ``url``.

        A registered exception is raised instead, which is how a test
        asks for a failing lookup.
        """
        self.requested_urls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    async def put(self, url, *, data, **_kwargs):
        """Record a write, raising whatever the test asked for."""
        self.put_calls.append((url, data))
        if self.put_error is not None:
            raise self.put_error

    async def patch(self, url, *, data, **_kwargs):
        """Record a check run update."""
        self.patch_calls.append((url, data))


def make_event(event, data):
    """Stand in for an octomachinery webhook event."""
    return SimpleNamespace(event=event, data=data)


@pytest.fixture
def make_gh_api():
    """Return a factory building a fake GitHub API client."""
    return FakeGitHubAPI
