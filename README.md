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
  skip-changelog: skip news  # default: `bot:chronographer:skip`

paths:  # relative modified file paths that do or don't need changelog mention
  exclude: []
  include: []

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

# Known issues/limitations

* Re-requesting a check run from Checks page in PRs doesn't always work.
  For a mysterious reason, [sometimes GitHub attaches a list of PRs to the events but sometimes that list is empty
  `[complain here]`](
  https://github.community/t5/GitHub-API-Development-and/BUG-Sometimes-rerequested-check-run-events-don-t-contain-a-PR/m-p/26964/thread-id/2189
  ). The link is historic and the discussion contents seem to have been
  lost during GitHub's platform migrations.
