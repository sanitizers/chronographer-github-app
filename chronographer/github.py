"""Interaction with GitHub API."""

from collections import defaultdict

import attr
from gidgethub.sansio import Event

from .config import BotAppConfig
from .utils import get_gh_jwt, get_install_token, GitHubAPIClient


GH_INSTALL_EVENTS = {'integration_installation', 'installation'}


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
        event = Event.from_http(
            request.headers,
            await request.read(),
            secret=self._config.webhook_secret,
        )
        await self.pre_process_webhook_event(event)
        return event

    async def pre_process_webhook_event(self, event):
        """Get an event object out of HTTP request."""
        action = event.data['action']
        if event.event in GH_INSTALL_EVENTS and action == 'created':
            await self.add_installation(event)

    async def __aenter__(self):
        """Store all installations data before starting."""
        # pylint: disable=attribute-defined-outside-init
        self._installations = await self.get_installations()
        return self

    async def __aexit__(self, *args, **kwargs):
        """Wipe out the installation store."""
        # pylint: disable=attribute-defined-outside-init
        self._installations = defaultdict(dict)

    @property
    def gh_jwt(self):
        """Generate app's JSON Web Token."""
        return get_gh_jwt(self._config.app_id, self._config.private_key)

    async def add_installation(self, event):
        """Retrieve an installation creds from store."""
        install = event.data['installation']
        install_id = install['id']
        self._installations[install_id] = {
            'data': install,
            'access': await get_install_token(
                app_id=self._config.app_id,
                private_key=self._config.private_key,
                access_token_url=install['access_tokens_url'],
            ),
        }
        return self._installations[install_id]

    async def get_installation(self, event):
        """Retrieve an installation creds from store."""
        install_id = event.data['installation']['id']
        return self._installations.get(install_id)

    async def get_installations(self):
        """Retrieve all installations with access tokens via API."""
        installations = defaultdict(dict)
        async with GitHubAPIClient() as gh_api:
            async for install in gh_api.getiter(
                    '/app/installations',
                    jwt=self.gh_jwt,
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
