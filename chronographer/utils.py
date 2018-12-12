"""Helper utils."""
from datetime import datetime, timezone
import sys
import time
import types
import typing

import aiohttp
import attr
import gidgethub.aiohttp
import jwt


APP_VERSION = 'unknown'  # TODO: add "/1.0" as in version
USER_AGENT = (
    f'Chronographer-Bot/{APP_VERSION}'
    ' (+https://github.com/sanitizers/chronographer-github-app)'
)


class SecretStr(str):
    """String that censors its __repr__ if called from another repr."""

    def __repr__(self):
        """Produce a string representation."""
        frame_depth = 1

        try:
            while True:
                frame = sys._getframe(  # pylint: disable=protected-access
                    frame_depth,
                )
                frame_depth += 1

                if frame.f_code.co_name == '__repr__':
                    return '<SECRET>'
        except ValueError:
            pass

        return super().__repr__()


@attr.dataclass  # pylint: disable=too-few-public-methods
class GitHubInstallationAccessToken:
    """Struct for installation access token response from GitHub API."""

    token: SecretStr = attr.ib(converter=SecretStr)
    """Access token for GitHub App Installation."""
    expires_at: datetime = attr.ib(
        converter=lambda date_string: datetime.strptime(
            date_string, '%Y-%m-%dT%H:%M:%SZ',  # empty %z isn't parsed well
        ).replace(tzinfo=timezone.utc),
    )
    """Token expiration time."""

    @property
    def expired(self):
        """Check whether this token has expired already."""
        return datetime.now(timezone.utc) > self.expires_at


@attr.dataclass
class GitHubAPIClient:
    """A client to the GitHub API with an asynchronous CM support."""

    _external_session: typing.Optional[aiohttp.ClientSession] = (
        attr.ib(default=None)
    )
    """A session created externally."""
    _current_session: aiohttp.ClientSession = attr.ib(init=False, default=None)
    """A session created per CM if there's no external one."""

    def _open_session(self) -> aiohttp.ClientSession:
        """Return a session to use with GitHub API."""
        assert self._current_session is None
        self._current_session = (
            aiohttp.ClientSession() if self._external_session is None
            else self._external_session
        )

    async def _close_session(self) -> aiohttp.ClientSession:
        """Free up the current session."""
        assert self._current_session is not None
        if self._external_session is None:
            await self._current_session.close()
        self._current_session = None

    async def __aenter__(self) -> gidgethub.aiohttp.GitHubAPI:
        """Return a GitHub API wrapper."""
        self._open_session()
        return gidgethub.aiohttp.GitHubAPI(
            self._current_session,
            USER_AGENT,
        )

    async def __aexit__(
            self,
            exc_type: typing.Optional[typing.Type[BaseException]],
            exc_val: typing.Optional[BaseException],
            exc_tb: typing.Optional[types.TracebackType]
    ) -> typing.Optional[bool]:
        """Close the current session resource."""
        await self._close_session()


def get_gh_jwt(app_id, private_key):
    """Create a signed JWT, valid for 60 seconds."""
    now = int(time.time())
    payload = {
        'iat': now,
        'exp': now + 60,
        'iss': app_id,
    }
    return jwt.encode(
        payload,
        key=private_key,
        algorithm='RS256',
    ).decode('utf-8')


async def get_install_token(*, app_id, private_key, access_token_url):
    """Retrieve installation access token from GitHub API."""
    gh_jwt = get_gh_jwt(app_id, private_key)
    async with GitHubAPIClient() as gh_api:
        return GitHubInstallationAccessToken(**(await gh_api.post(
            access_token_url,
            data=b'',
            jwt=gh_jwt,
            accept='application/vnd.github.machine-man-preview+json',
        )))
