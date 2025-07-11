FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get -y update && \
    apt-get -y install python3-dev build-essential curl pkg-config

RUN uv init

RUN uv add mlflow boto3 psycopg2-binary

CMD ["bash"]