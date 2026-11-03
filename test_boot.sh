#! /usr/bin/env bash
# Check that the app can start up under the current interpreter.
#
# It boots `python -m chronographer` against a throwaway GitHub App
# identity. Authenticating that identity is *expected* to fail — what this
# checks is everything that has to work before that: the config loading, the
# event loop bootstrap, the `anyio` runner, the aiohttp client session and the
# GitHub App wrapper.
#
# Regression guard for the Python 3.14 deployment: gh-63.

set -euo pipefail

BOOT_TIMEOUT="${BOOT_TIMEOUT:-30}"
BOOT_MARKER='private key SHA-1 fingerprint'

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

>&2 echo ====================================================================
>&2 echo Booting the app under "$(python -V)"
>&2 echo ====================================================================

openssl genrsa -out "${tmp_dir}/throwaway-key.pem" 2048 2>/dev/null

exit_code=0
env \
  HOST=localhost \
  PORT="${PORT:-8080}" \
  ENV=dev \
  DEBUG=true \
  GITHUB_APP_IDENTIFIER=99999 \
  GITHUB_PRIVATE_KEY="$(cat "${tmp_dir}/throwaway-key.pem")" \
  timeout "${BOOT_TIMEOUT}" python -m chronographer \
  > "${tmp_dir}/boot.log" 2>&1 || exit_code=$?

if ! grep -qF "${BOOT_MARKER}" "${tmp_dir}/boot.log"
then
    >&2 echo "The app did not reach the GitHub App set-up stage" \
             "(exit code ${exit_code}). Its output was:"
    >&2 cat "${tmp_dir}/boot.log"
    exit 1
fi

>&2 echo The app booted and reached the GitHub App set-up stage.
