ARG AIRFLOW_IMAGE_NAME
FROM ${AIRFLOW_IMAGE_NAME}

# The `uv` tools is Rust packaging tool that is much faster than `pip` and other installer
# Support for uv as installation tool is experimental

COPY pyproject.toml ./

RUN uv pip install --no-cache --group airflow-server