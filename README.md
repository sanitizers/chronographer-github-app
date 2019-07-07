[![Linux build @ Travis CI](https://img.shields.io/travis/com/sanitizers/chronographer-github-app/master.svg?label=Linux%20build%20%40%20Travis%20CI)](https://travis-ci.com/sanitizers/chronographer-github-app)

# chronographer-github-app
Your severe chronographer who is watching you record all the news to change note files!

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

## Heroku notes

```console
heroku buildpacks:add --index 1 https://github.com/ianpurvis/heroku-buildpack-version.git --app=sanitizers-chronographer-bot
```

# Known issues/limitations

* Re-requesting a check run from Checks page in PRs doesn't always work.
  For a mysterious reason, [sometimes GitHub attaches a list of PRs to the events but sometimes that list is empty
  `[complain here]`](
  https://github.community/t5/GitHub-API-Development-and/BUG-Sometimes-rerequested-check-run-events-don-t-contain-a-PR/m-p/26964/thread-id/2189
  )
