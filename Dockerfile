FROM python:3.7-slim

LABEL "maintainer"="Sviatoslav Sydorenko <wk+github-actions@sydorenko.org.ua>"
LABEL "repository"="https://github.com/sanitizers/chronographer-github-app"
LABEL "homepage"="https://github.com/sanitizers/chronographer-github-app"

LABEL "com.github.actions.name"="chronographer"
LABEL "com.github.actions.description"="Run a news fragment presence check"
LABEL "com.github.actions.icon"="file-text"
LABEL "com.github.actions.color"="#0076df"

ADD . chronographer
WORKDIR chronographer
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "-m", "chronographer.action"]
