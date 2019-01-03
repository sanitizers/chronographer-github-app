"""Interaction with GitHub API."""

from collections import defaultdict
from datetime import datetime
import typing

import attr
from gidgethub.sansio import Event

from .config import BotAppConfig
from .utils import (
    amap, convert_datetime, dict_to_kwargs_cb,
    get_gh_jwt, get_install_token,
    GitHubAPIClient,
)


GH_INSTALL_EVENTS = {'integration_installation', 'installation'}


import contextvars
gh_app = contextvars.ContextVar('github_app', default='default_val')
gh_app.set('some_val')
def __getattr__(attr):
    if attr == 'app':
        return gh_app.get()
    raise AttributeError


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
        action = event.data.get('action')
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
            'data': GitHubAppInstallation(install),
            'access': await get_install_token(
                app_id=self._config.app_id,
                private_key=self._config.private_key,
                access_token_url=install['access_tokens_url'],
            ),
        }
        return self._installations[install_id]

    async def get_installation(self, event):
        """Retrieve an installation creds from store."""
        if event.event == 'ping':
            return None

        install_id = event.data['installation']['id']
        return self._installations.get(install_id)

    async def get_installations(self):
        """Retrieve all installations with access tokens via API."""
        installations = defaultdict(dict)
        async with GitHubAPIClient() as gh_api:
            async for install in amap(
                    dict_to_kwargs_cb(GitHubAppInstallation),
                    gh_api.getiter(
                        '/app/installations',
                        jwt=self.gh_jwt,
                        accept=''
                        'application/vnd.github.machine-man-preview+json',
                    ),
            ):
                installations[install.id] = {
                    'data': install,
                    'access': await get_install_token(
                        app_id=self._config.app_id,
                        private_key=self._config.private_key,
                        access_token_url=install.access_tokens_url,
                    ),
                }
        return installations


@attr.dataclass  # pylint: disable=too-few-public-methods
class GitHubAppInstallation:
    """
    Represents a GitHub App installed into a user or an organization profile.

    It has its own ID for installation which is a unique combo of an app
    and a profile (user or org).
    """

    id: int = attr.ib(converter=int)
    """Installation ID."""
    app_id: int = attr.ib(converter=int)
    """GitHub App ID."""

    created_at: datetime = attr.ib(converter=convert_datetime)
    """Date time when the installation has been installed."""
    updated_at: datetime = attr.ib(converter=convert_datetime)
    """Date time when the installation was last updated."""

    account: dict
    """Target account (org or user) where this GitHub App is installed into."""
    events: typing.List[str]
    """List of webhook events the app will be receiving from the account."""
    permissions: dict
    """Permission levels of access to API endpoints types."""
    repository_selection: str = attr.ib(converter=str)
    """Repository selection mode."""
    single_file_name: typing.Optional[str]
    """File path the GitHub app controls."""

    target_id: int = attr.ib(converter=int)
    """Target account ID where this GitHub App is installed into."""
    target_type: str = attr.ib(
        validator=attr.validators.in_(('Organization', 'User')),
    )
    """Target account type where this GitHub App is installed into."""

    access_tokens_url: str = attr.ib(converter=str)
    """API endpoint to retrieve access token from."""
    html_url: str = attr.ib(converter=str)
    """URL for controlling the GitHub App Installation."""
    repositories_url: str = attr.ib(converter=str)
    """API endpoint listing repositories accissible by this Installation."""
