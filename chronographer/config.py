"""GitHub App/bot configuration."""

from functools import lru_cache

import environ
import envparse

from octomachinery.app.runtime.config import RuntimeConfig
from octomachinery.app.runtime.utils import _ContextMap
from octomachinery.github.config.app import GitHubAppIntegrationConfig


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
    class WebServerConfig:
        """Config of a web-server."""

        host = environ.var('0.0.0.0', name='HOST')
        port = environ.var(8080, name='PORT', converter=int)

    github = environ.group(GitHubAppIntegrationConfig)
    server = environ.group(WebServerConfig)
    runtime = environ.group(RuntimeConfig)
