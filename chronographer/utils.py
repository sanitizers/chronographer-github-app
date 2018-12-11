"""Helper utils."""
from datetime import datetime, timezone
import sys
import time

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
    async with aiohttp.ClientSession() as session:
        gh_api = gidgethub.aiohttp.GitHubAPI(
            session,
            USER_AGENT,
            jwt=gh_jwt,
        )
        return await gh_api.getitem(access_token_url)['token']
