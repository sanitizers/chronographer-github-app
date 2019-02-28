[![Linux build @ Travis CI](https://img.shields.io/travis/com/sanitizers/chronographer-github-app/master.svg?label=Linux%20build%20%40%20Travis%20CI)](https://travis-ci.com/sanitizers/chronographer-github-app)

# chronographer-github-app
Your severe chronographer who is watching you record all the news to change note files!

# Running the app
## Local development
1. Copy a dotenv config template: `cp -v .env{.example,}`
2. Change `GITHUB_APP_IDENTIFIER` value and `GITHUB_PRIVATE_KEY` contents
   * You should be able to inline the key using a trick like this:
   ```console
   echo -n "GITHUB_PRIVATE_KEY='$(cat /path/to/app.date.private-key.pem | sed ':a;N;$!ba;s/\n/\\\\n/g')'" >> .env
   ```
3. `python3.7 -m chronographer`

## Heroku notes

```console
heroku buildpacks:add --index 1 https://github.com/ianpurvis/heroku-buildpack-version.git --app=sanitizers-chronographer-bot
```
