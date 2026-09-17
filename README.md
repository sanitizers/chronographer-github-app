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
   cat $GITHUB_PRIVATE_KEY_PATH | python3 -c 'import sys; inline_private_key=r"\n".join(map(str.strip, sys.stdin.readlines())); print(f"GITHUB_PRIVATE_KEY='"'"'{inline_private_key}'"'"'", end="")' >> .env
   ```
3. `python3 -m chronographer`

## Checking that the app boots
`./test_boot.sh` starts the app against a throwaway GitHub App identity under
whatever `python` is on `PATH`. Authenticating that identity is *expected* to
fail — what the script checks is everything that has to work before that: the
dotenv config loading, the event loop bootstrap, the `anyio` runner, the
aiohttp client session and the GitHub App wrapper. It is how to tell whether a
given interpreter can run this app at all, without deploying it.

# Known issues/limitations

* Re-requesting a check run from Checks page in PRs doesn't always work.
  For a mysterious reason, [sometimes GitHub attaches a list of PRs to the events but sometimes that list is empty
  `[complain here]`](
  https://github.community/t5/GitHub-API-Development-and/BUG-Sometimes-rerequested-check-run-events-don-t-contain-a-PR/m-p/26964/thread-id/2189
  ). The link is historic and the discussion contents seem to have been
  lost during GitHub's platform migrations.
* `octomachinery` caps `anyio` below v2, and `anyio` v1 starts the app via
  `asyncio.get_event_loop()`, relying on it to implicitly create a loop.
  Python 3.14 removed that fallback, so `chronographer/__main__.py` creates
  the loop itself. That workaround can go away once `octomachinery` supports
  `anyio` v2+. The GitHub Action entry point never needed it.
* Installing the lock file under Python 3.14 builds `cffi` from source — the
  pinned version predates CPython 3.14 and ships no wheel for it. Deployment
  images need a C compiler and the libffi headers until that pin moves.
