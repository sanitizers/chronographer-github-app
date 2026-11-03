"""Tests for the repository config retrieval helpers."""

import asyncio
import http

import gidgethub
import pytest

from chronographer import file_utils

# pylint: disable=redefined-outer-name,unused-argument


PYPROJECT_TOML = """\
[tool.towncrier]
directory = "changelog.d"
filename = "CHANGELOG.rst"
"""


@pytest.fixture
def fake_repo_files(monkeypatch):
    """Serve repository file contents from an in-memory mapping."""
    def _serve(files):
        requested = []

        async def _read_file_contents_from_repo(*, file_path, ref=None):
            requested.append(file_path)
            try:
                content = files[file_path]
            except KeyError:
                return None
            if isinstance(content, Exception):
                raise content
            return content

        monkeypatch.setattr(
            file_utils,
            'read_file_contents_from_repo',
            _read_file_contents_from_repo,
        )
        return requested

    return _serve


def test_towncrier_config_falls_back_to_pyproject(fake_repo_files):
    """Check that ``pyproject.toml`` is tried after ``towncrier.toml``."""
    requested = fake_repo_files({'pyproject.toml': PYPROJECT_TOML})

    config = asyncio.run(
        file_utils.get_towncrier_config(towncrier_config_filename=None),
    )

    assert requested == ['towncrier.toml', 'pyproject.toml']
    assert config['directory'] == 'changelog.d'


def test_explicit_towncrier_config_filename_is_the_only_candidate(
        fake_repo_files,
):
    """Check that a configured filename disables candidate probing."""
    requested = fake_repo_files({'custom.toml': PYPROJECT_TOML})

    config = asyncio.run(
        file_utils.get_towncrier_config(
            towncrier_config_filename='custom.toml',
        ),
    )

    assert requested == ['custom.toml']
    assert config['filename'] == 'CHANGELOG.rst'


def test_missing_towncrier_config_yields_no_section(fake_repo_files):
    """Check that an absent config file produces no towncrier section."""
    fake_repo_files({})

    assert asyncio.run(
        file_utils.get_towncrier_config(towncrier_config_filename=None),
    ) is None


def test_towncrier_section_absent_from_pyproject(fake_repo_files):
    """Check that an unrelated ``pyproject.toml`` yields no section."""
    fake_repo_files({'pyproject.toml': '[tool.pytest]\naddopts = ""\n'})

    assert asyncio.run(
        file_utils.get_towncrier_config(towncrier_config_filename=None),
    ) is None


def test_rejected_candidate_does_not_abort_the_lookup(fake_repo_files):
    """Check that a rejected candidate lets the next one be tried."""
    requested = fake_repo_files({
        'towncrier.toml': gidgethub.BadRequest(http.HTTPStatus(404)),
        'pyproject.toml': PYPROJECT_TOML,
    })

    config = asyncio.run(
        file_utils.get_towncrier_config(towncrier_config_filename=None),
    )

    assert requested == ['towncrier.toml', 'pyproject.toml']
    assert config['directory'] == 'changelog.d'


def test_chronographer_config_falls_back_to_shared_config(monkeypatch):
    """Check that ``.github/config.yml`` backs up a missing app config."""
    requested = []

    async def _get_installation_config(*, config_name=None, ref=None):
        requested.append(config_name)
        if config_name == 'chronographer.yml':
            raise gidgethub.BadRequest(http.HTTPStatus(404))
        return {'chronographer': {'branch-protection-check-name': 'chng'}}

    monkeypatch.setattr(
        file_utils, 'get_installation_config', _get_installation_config,
    )

    config = asyncio.run(file_utils.get_chronographer_config())

    assert requested == ['chronographer.yml', None]
    assert config == {'branch-protection-check-name': 'chng'}


def test_shared_config_without_a_chronographer_section(monkeypatch):
    """Check that an unrelated shared config yields an empty mapping."""
    async def _get_installation_config(*, config_name=None, ref=None):
        if config_name == 'chronographer.yml':
            raise gidgethub.BadRequest(http.HTTPStatus(404))
        return {'other-app': {'setting': 1}}

    monkeypatch.setattr(
        file_utils, 'get_installation_config', _get_installation_config,
    )

    assert asyncio.run(file_utils.get_chronographer_config()) == {}
