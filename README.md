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

paths:  # relative modified file paths that do or don't need changelog mention
  exclude: []
  include: []
  towncrier-config-filename: ~  # default: `~`, which means checking both

...
```

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
