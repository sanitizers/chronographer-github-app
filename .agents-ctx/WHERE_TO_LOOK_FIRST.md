# Where to Look First

When picking up a task, get oriented before proposing anything.
Read, in this order:

1. The packaging metadata -- what the project is, what it depends
   on, what it exposes.
2. The source of the module the task is about.
3. The shared test fixtures, then the tests for that module --
   they are the behavioral contract.
4. `tox.ini` and `.pre-commit-config.yaml` -- how things get run
   locally and in CI.
5. The main CI/CD workflow.

Here:

1. `requirements.in` -- the direct dependencies, pinned into
   `requirements.txt` with pip-tools (`.pip-tools.toml`). There's
   no packaging metadata.
2. `chronographer/event_handlers.py` -- the webhook handlers --
   and `chronographer/__main__.py`, `action.py` for the GitHub
   Action mode.
3. There's no test suite; see `test_bot.sh` and `test_action.sh`,
   which replay the sample `*_event.json` payloads.
4. `.pre-commit-config.yaml` -- there's no `tox.ini`.
5. `Procfile`, `runtime.txt`, `app.sh` and `Dockerfile` -- how the
   service is deployed.

Other places worth knowing:

- `README.md` -- the configuration the app reads from repositories
  it's installed in.
