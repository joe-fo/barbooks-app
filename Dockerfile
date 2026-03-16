# --- build stage ---
FROM python:3.11-slim@sha256:06fa338add3c2ab8daeff7304a6bb204c68f67743b13553a8999605fc8097c58 AS build

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only=main --no-root

# --- runtime stage ---
FROM python:3.11-slim@sha256:06fa338add3c2ab8daeff7304a6bb204c68f67743b13553a8999605fc8097c58

RUN useradd --system --uid 1001 --no-create-home appuser

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000

USER appuser
EXPOSE 8000 8501
