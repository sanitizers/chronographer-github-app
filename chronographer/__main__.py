"""Cronicler robot runner."""

from octomachinery.app.server.runner import run as run_app
from octomachinery.utils.versiontools import get_version_from_scm_tag
from octomachinery.app.github import GitHubApplication

from . import event_handlers  # noqa: F401; pylint: disable=unused-import


#app = GitHubApplication()


__name__ == '__main__' and GitHubApplication.run_simple(  # pylint: disable=expression-not-assigned
    name='Chronographer-Bot',
    version=get_version_from_scm_tag(root='..', relative_to=__file__),
    url='https://github.com/apps/chronographer',
)
#__name__ == '__main__' and run_app(  # pylint: disable=expression-not-assigned
#    name='Chronographer-Bot',
#    version=get_version_from_scm_tag(root='..', relative_to=__file__),
#    url='https://github.com/apps/chronographer',
#)
