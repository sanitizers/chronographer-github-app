"""GitHub App/bot configuration."""

from contextvars import ContextVar
from functools import lru_cache

import attr
import environ
import envparse

from .utils import SecretStr, USER_AGENT


class _ContextMap:
    __slots__ = '__map__', '__token_map__'

    def __init__(self, **initial_vars):
        self.__map__ = {k: ContextVar(v) for k, v in initial_vars.items()}
        """Storage for all context vars."""

        self.__token_map__ = {}
        """Storage for individual context var reset tokens."""

    def __getattr__(self, name):
        if name in ('__map__', '__token_map__'):
            return getattr(self, name)
        try:
            return self.__map__[name].get()
        except LookupError:
            raise AttributeError

    def __setattr__(self, name, value):
        if name in ('__map__', '__token_map__'):
            object.__setattr__(self, name, value)
        elif name in self.__map__:
            reset_token = self.__map__[name].set(value)
            self.__token_map__[name] = reset_token
        else:
            raise AttributeError

    def __delattr__(self, name):
        if name not in self.__map__:
            raise AttributeError
        reset_token = self.__token_map__[name]
        self.__map__[name].reset(reset_token)
        del self.__token_map__[name]


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
    class RuntimeConfig:
        """Config of runtime env."""

        debug = environ.bool_var(False, name='DEBUG')
        env = environ.var(
            'prod', name='ENV',
            validator=attr.validators.in_(('dev', 'prod')),
        )

    @environ.config  # pylint: disable=too-few-public-methods
    class WebServerConfig:
        """Config of a web-server."""

        host = environ.var('0.0.0.0', name='HOST')
        port = environ.var(8080, name='PORT', converter=int)

    github = environ.group(GitHubAppIntegrationConfig)
    server = environ.group(WebServerConfig)
    runtime = environ.group(RuntimeConfig)
