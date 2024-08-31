"""Utility helpers for getting files from App/Action installations."""

import contextlib
import tomllib
import typing

import gidgethub

from octomachinery.app.runtime.installation_utils import (
    get_installation_config,
    read_file_contents_from_repo,
)


async def parse_towncrier_config(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Fetch and parse a toml config file contents as dict."""
    for towncrier_config_filename in 'towncrier.toml', 'pyproject.toml':
        with contextlib.suppress(gidgethub.BadRequest):
            config_content = await read_file_contents_from_repo(
                file_path=towncrier_config_filename,
                ref=ref,
            )
            break
    else:
        return {}

    return tomllib.loads(config_content)


async def get_towncrier_config(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Retrieve towncrier section from pyproject.toml file."""
    pyproject_toml = await parse_towncrier_config(ref=ref)
    return pyproject_toml.get('tool', {}).get('towncrier')


async def get_chronographer_config(
        *,
        ref: typing.Optional[str] = None,
) -> typing.Mapping[str, typing.Any]:
    """Return chronographer config ``.github/chronographer.yml`` object.

    If the file is not there, fall back to ``.github/config.yml``
    """
    try:
        return await get_installation_config(
            config_name='chronographer.yml',
            ref=ref,
        )
    except gidgethub.BadRequest:
        pass

    config_json = await get_installation_config(ref=ref)
    return config_json.get('chronographer', {})
