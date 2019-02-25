"""Helper utils."""

import time

import jwt

from octomachinery.github.api.client import GitHubAPIClient
from octomachinery.github.models import GitHubInstallationAccessToken


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
