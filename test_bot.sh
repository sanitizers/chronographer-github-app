#! /usr/bin/env bash

GITHUB_APP_WEBHOOKS_URL=http://localhost:8080
>&2 echo ====================================================================
>&2 echo Running Basic Funcionality test against "${GITHUB_APP_WEBHOOKS_URL}"
>&2 echo ====================================================================
>&2 echo

for event in ping security_advisory pull_request check_run
do
    GITHUB_EVENT_PATH="`pwd`/${event}_event.json"
    >&2 echo Testing "${event}"...
    curl \
      -H "X-GitHub-Event:${event}" \
      -H "X-GitHub-Delivery:$(uuidgen -r)" \
      -H 'Content-Type:application/json' \
      --data "@${GITHUB_EVENT_PATH}" \
      "${GITHUB_APP_WEBHOOKS_URL}"
    >&2 echo
    >&2 echo

    sleep 2
done
