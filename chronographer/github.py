"""Interaction with GitHub API."""

from collections import defaultdict

import aiohttp
import attr
import gidgethub.aiohttp
from gidgethub.sansio import Event

from .config import BotAppConfig
from .utils import get_gh_jwt, get_install_token, USER_AGENT


@attr.dataclass
class GitHubApp:
    """GitHub API wrapper."""

    _config: BotAppConfig.GitHubAppIntegrationConfig

    def __attrs_post_init__(self):
        """Initialize installations store."""
        # pylint: disable=attribute-defined-outside-init
        self._installations = defaultdict(dict)

    async def event_from_request(self, request):
        """Get an event object out of HTTP request."""
        return Event.from_http(
            request.headers,
            await request.read(),
            secret=self._config.webhook_secret,
        )

    async def __aenter__(self):
        """Store all installations data before starting."""
        # pylint: disable=attribute-defined-outside-init
        self._installations = await self.get_installations()
        return self

    async def __aexit__(self, *args, **kwargs):
        """Wipe out the installation store."""
        # pylint: disable=attribute-defined-outside-init
        self._installations = defaultdict(dict)

    async def get_installation(self, event):
        """Retrieve an installation creds from store."""
        install_id = event.data['installation']['id']
        return self._installations.get(install_id)

    async def get_installations(self):
        """Retrieve all installations with access tokens via API."""
        installations = defaultdict(dict)
        gh_jwt = get_gh_jwt(self._config.app_id, self._config.private_key)
        async with aiohttp.ClientSession() as session:
            gh_api = gidgethub.aiohttp.GitHubAPI(
                session,
                USER_AGENT,
            )
            async for install in gh_api.getiter(
                    '/app/installations',
                    jwt=gh_jwt,
                    accept='application/vnd.github.machine-man-preview+json',
            ):
                installations[install['id']] = {
                    'data': install,
                    'access': await get_install_token(
                        app_id=self._config.app_id,
                        private_key=self._config.private_key,
                        access_token_url=install['access_tokens_url'],
                    ),
                }
        return installations
