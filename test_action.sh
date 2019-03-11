#! /usr/bin/env bash

GITHUB_ACTION_PYTHON_MODULE=chronographer.action
>&2 echo ========================================================================
>&2 echo Running Basic Funcionality test against "${GITHUB_ACTION_PYTHON_MODULE}"
>&2 echo ========================================================================
>&2 echo

for event in ping pull_request check_run
do
    >&2 echo Testing "${event}"...
    GITHUB_EVENT_NAME="${event}" \
    GITHUB_EVENT_PATH="`pwd`/${event}_event.json" \
    python -m "${GITHUB_ACTION_PYTHON_MODULE}"
    >&2 echo
    >&2 echo

    sleep 2
done
