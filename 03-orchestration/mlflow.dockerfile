FROM python:3.12-slim as builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=../uv.lock,target=uv.lock \
    --mount=type=bind,source=../pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

ADD ../. /app/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Multistage building
FROM python:3.12-slim

COPY --from=builder --chown=app:app /app/.venv /app/.venv

EXPOSE 5000

# Launch mlflow via uv
CMD [ "uv" " run" \
    "mlflow", "server", \
    "--backend-store-uri", "sqlite:///home/mlflow_data/mlflow.db", \
    "--host", "0.0.0.0", \
    "--port", "5000" \
]