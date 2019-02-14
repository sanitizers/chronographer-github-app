"""GitHub App/bot configuration."""

from functools import lru_cache

import environ
import envparse

from octomachinery.app.runtime.config import RuntimeConfig
from octomachinery.app.server.config import WebServerConfig
from octomachinery.github.config.app import GitHubAppIntegrationConfig


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

    github = environ.group(GitHubAppIntegrationConfig)
    server = environ.group(WebServerConfig)
    runtime = environ.group(RuntimeConfig)
