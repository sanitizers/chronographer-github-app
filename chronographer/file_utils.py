"""Utility helpers for getting files from App/Action installations."""

import typing

import gidgethub
import toml

from octomachinery.app.runtime.installation_utils import (
    read_file_contents_from_repo,
)


async def read_pyproject_toml(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Fetch and parse pyproject.toml contents as dict."""
    try:
        config_content = await read_file_contents_from_repo(
            file_path='pyproject.toml',
            ref=ref,
        )
    except gidgethub.BadRequest:
        config_content = None

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
