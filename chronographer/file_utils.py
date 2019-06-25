"""Utility helpers for getting files from App/Action installations."""

from io import StringIO
import typing

import toml
import yaml

from octomachinery.app.runtime.context import RUNTIME_CONTEXT
from octomachinery.app.runtime.installation_utils import (
    _get_file_contents_from_fs,
    _get_file_contents_from_api,
)


async def read_file_contents_from_repo(
        *,
        file_path: str,
        ref: typing.Optional[str] = None,
) -> str:
    """Get a config object from the current installation.

    Read from file system checkout in case of GitHub Action env.
    Grab it via GitHub API otherwise.

    Usage::

        >>> from octomachinery.app.runtime.installation_utils import (
        ...     read_file_contents_from_repo
        ... )
        >>> await read_file_contents_from_repo(
        ...     '/file/path.txt',
        ...     ref='bdeaf38',
        ... )
    """
    if RUNTIME_CONTEXT.IS_GITHUB_ACTION and ref is None:
        return _get_file_contents_from_fs(file_path)

    return await _get_file_contents_from_api(file_path, ref)


async def get_installation_config(
        *,
        config_name: str = 'config.yml',
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Get a config object from the current installation.

    Read from file system checkout in case of GitHub Action env.
    Grab it via GitHub API otherwise.

    Usage::

        >>> from octomachinery.app.runtime.installation_utils import (
        ...     get_installation_config
        ... )
        >>> await get_installation_config()
    """
    config_path = f'.github/{config_name}'

    config_content = await read_file_contents_from_repo(
        file_path=config_path,
        ref=ref,
    )

    if config_content is None:
        return {}

    return yaml.load(StringIO(config_content))


async def read_pyproject_toml(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Fetch and parse pyproject.toml contents as dict."""
    config_content = await read_file_contents_from_repo(
        file_path='pyproject.toml',
        ref=ref,
    )

    if config_content is None:
        return {}

    return toml.loads(config_content)


async def get_towncrier_config(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Retrieve towncrier section from pyproject.toml file."""
    pyproject_toml = await read_pyproject_toml(ref=ref)
    return pyproject_toml.get('tool', {}).get('towncrier')
