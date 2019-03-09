#! /usr/bin/env bash

GITHUB_APP_WEBHOOKS_URL=http://localhost:8080
>&2 echo ====================================================================
>&2 echo Running Basic Funcionality test against "${GITHUB_APP_WEBHOOKS_URL}"
>&2 echo ====================================================================
>&2 echo

>&2 echo Testing ping...
curl \
  -H 'X-GitHub-Event:ping' \
  -H 'X-GitHub-Delivery:cxxx-Ping-delivery' \
  -H 'Content-Type:application/json' \
  --data-raw '
  {
    "hook": {"app_id": 0},
    "hook_id": 0,
    "zen": "Hey zen!"
  }
  ' "${GITHUB_APP_WEBHOOKS_URL}"
>&2 echo
>&2 echo

sleep 2

>&2 echo Testing pull_request...
curl \
  -H 'X-GitHub-Event:pull_request' \
  -H 'X-GitHub-Delivery:cxxx-PR-delivery' \
  -H 'Content-Type:application/json' \
  --data-raw '
  {
    "action": "synchronize",
    "sender": {"login": "curl"},
    "number": 2,
    "installation": {"id": 491111},
    "repository": {"full_name": "sanitizers/browntruck"},
    "pull_request": {
      "number": 2,
      "head": {
        "ref": "feature/github-app-aiohttp",
        "sha": "713a1820272569204d70eb28bfbf997e2a3bd121"
      },
      "diff_url":
      "https://patch-diff.githubusercontent.com/raw/sanitizers/browntruck/pull/2.diff"
    }
  }
  ' "${GITHUB_APP_WEBHOOKS_URL}"
>&2 echo
>&2 echo

sleep 2

>&2 echo Testing check_run...
curl \
  -H 'X-GitHub-Event:check_run' \
  -H 'X-GitHub-Delivery:cxxx-Check-Run-delivery' \
  -H 'Content-Type:application/json' \
  --data-raw '
  {
    "check_run": {
      "conclusion": "",
      "name": "",
      "check_suite": {
        "id": 0,
        "pull_requests": [
          {
            "number": 1,
            "head": {
              "ref": "feature/github-app-aiohttp",
              "sha": "f2114ef"
            }
          }
        ]
      }
    },
    "requested_action": {"identifier": 0},
    "action": "rerequested",
    "installation": {"id": 491111},
    "repository": {"full_name": "sanitizers/browntruck"}
  }
  ' "${GITHUB_APP_WEBHOOKS_URL}"
>&2 echo
>&2 echo
