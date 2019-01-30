"""GitHub App/bot configuration."""

from functools import lru_cache

import environ
import envparse

from octomachinery.app.runtime.config import RuntimeConfig
from octomachinery.app.runtime.utils import _ContextMap
from octomachinery.github.models.utils import SecretStr

from .utils import USER_AGENT


RUNTIME_CONTEXT = _ContextMap(
    app_installation='app installation',
    config='config context',
    github_app='github app',
)


def load_dotenv():
    """Read .env into env vars."""
    envparse.Env.read_envfile()


@lru_cache(maxsize=1)
def get_config():
    """Return an initialized config instance."""
    return environ.to_config(BotAppConfig)


@environ.config  # pylint: disable=too-few-public-methods
class BotAppConfig:
    """Bot app config."""

    @environ.config  # pylint: disable=too-few-public-methods
    class GitHubAppIntegrationConfig:
        """GitHub App auth related config."""

        app_id = environ.var(name='GITHUB_APP_IDENTIFIER')
        private_key = environ.var(
            name='GITHUB_PRIVATE_KEY',
            converter=SecretStr,
        )
        webhook_secret = environ.var(
            None, name='GITHUB_WEBHOOK_SECRET',
            converter=lambda s: SecretStr(s) if s is not None else s,
        )

        user_agent = USER_AGENT

    @environ.config  # pylint: disable=too-few-public-methods
    class WebServerConfig:
        """Config of a web-server."""

        host = environ.var('0.0.0.0', name='HOST')
        port = environ.var(8080, name='PORT', converter=int)

    github = environ.group(GitHubAppIntegrationConfig)
    server = environ.group(WebServerConfig)
    runtime = environ.group(RuntimeConfig)
