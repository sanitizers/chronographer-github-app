FROM python:3.7-slim

LABEL "maintainer"="Sviatoslav Sydorenko <wk+github-actions@sydorenko.org.ua>"
LABEL "repository"="https://github.com/sanitizers/chronographer-github-app"
LABEL "homepage"="https://github.com/sanitizers/chronographer-github-app"

LABEL "com.github.actions.name"="chronographer"
LABEL "com.github.actions.description"="Run a news fragment presence check"
LABEL "com.github.actions.icon"="file-text"
LABEL "com.github.actions.color"="#0076df"

ADD . /usr/src/chronographer
RUN pip install -r /usr/src/requirements.txt

ENV PYTHONPATH /usr/src/chronographer

ENTRYPOINT ["python", "-m", "chronographer.action"]
