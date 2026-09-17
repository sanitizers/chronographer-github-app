# chronographer-github-app
Your severe chronographer who is watching you record all the news to change note files!

# Configuring the installed app

Here's an example configuration file that a repository where Chronographer
is installed can use optionally, to set certain aspects of this
GitHub App's behavior:
```yaml
# .github/chronographer.yml
---

action-hints:
  # check-title-prefix: chng  # default: `{{ branch-protection-check-name }}: `
  external-docs-url: https://pip.pypa.io/how-to-changelog
  inline-markdown: >
    Check out https://pip.pypa.io/how-to-changelog

branch-protection-check-name: Timeline protection

enforce-name:
  suffix: .rst  # can be empty or `.md` too

exclude:
  bots:
  - dependabot-preview
  - dependabot
  - patchback
  humans:
  - pyup-bot

labels:
  fragment-provided: change note detected  # default: `bot:chronographer:provided`, disable with `~`
  skip-changelog: skip news  # default: `bot:chronographer:skip`

# Labels that demand a change note of a particular towncrier type.  A
# label only asks for something while it is set on the pull request, and
# one fragment of any of the listed types settles it.  Several labels at
# once means several demands, each needing its own fragment:
require-change-types:
  enhancement:
  - contrib
  - feature
  bug:
  - bugfix

paths:  # relative modified file paths that do or don't need changelog mention
  exclude: []
  include: []
  towncrier-config-filename: ~  # default: `~`, which means checking both

...
```

# Creating change notes from the check run

A failing check run offers up to three buttons, one per change note type,
that commit an empty change note to the pull request branch. The file is
seeded with the pull request title so that reviewers can refine it through
suggested changes rather than having to write it from scratch.

The types the pull request labels ask for through `require-change-types`
come first; the rest of the towncrier types fill whatever room is left of
the three slots the Checks API allows. A type whose name does not fit into
an action identifier -- 13 characters, once the namespace prefix is
accounted for -- is not offered.

This needs the App to hold the `contents: write` permission, and the
commit lands on the head branch, so it only works while the head
repository is still around. When the push is refused, the check run says
so instead of failing silently.

# Running the app
## Local development
1. Copy a dotenv config template: `cp -v .env{.example,}`
2. Change `GITHUB_APP_IDENTIFIER` value and `GITHUB_PRIVATE_KEY` contents
   * You should be able to inline the key using a trick like this:
   ```console
   GITHUB_PRIVATE_KEY_PATH=~/Downloads/your-app-slug.2019-03-24.private-key.pem
   cat $GITHUB_PRIVATE_KEY_PATH | python3.7 -c 'import sys; inline_private_key=r"\n".join(map(str.strip, sys.stdin.readlines())); print(f"GITHUB_PRIVATE_KEY='"'"'{inline_private_key}'"'"'", end="")' >> .env
   ```
3. `python3.7 -m chronographer`

# Running the tests
```console
$ python -Im pip install -r requirements.txt
$ python -Im pip install pytest
$ python -Im pytest
```

The linters run the same way, PyLint included — pre-commit.ci skips that
one because `local` hooks cannot run there:
```console
$ python -Im pre_commit run --all-files
```

# Known issues/limitations

* Re-requesting a check run used to be documented here as failing "for a
  mysterious reason" whenever GitHub sent an empty list of PRs with the
  event. It is not mysterious: the `pull_requests` array of a check suite
  only lists pull requests whose head branch lives in *this* repository, so
  it is empty for every PR sent from a fork. The entries it does carry are
  stub objects without `user`, `labels` or `issue_url`. Both cases are now
  handled by looking the pull request up through the API instead of reading
  it out of the webhook payload.
