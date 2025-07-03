FROM python:3.12-slim as builder
# use bytecode to quicken build, use mode copy istead of symllnking for safety
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Use system built-in pyton instead downloading it
ENV UV_PYTHON_DOWNLOADS=0


COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --group mlflow-server --no-dev --no-default-groups

ADD . /app

# in our cause we don't seed to install project code at all, since \
# mlflow will be receiving data from API requests or Airflow within compose
#RUN --mount=type=cache,target=/root/.cache/uv \
#    uv sync --locked

# Multistage building
FROM python:3.12-slim

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

# Launch mlflow via uv
CMD [ "mlflow", "server", \
    "--backend-store-uri", "sqlite:///home/mlflow_data/mlflow.db", \
    "--host", "0.0.0.0", \
    "--port", "5000" \
    ]