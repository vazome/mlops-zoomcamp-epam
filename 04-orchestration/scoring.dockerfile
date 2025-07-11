FROM agrigorev/zoomcamp-model:mlops-2024-3.10.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY scoring.py scoring.py

RUN uv pip install --system pandas pyarrow scikit-learn

# Run script, if no arguments provided in docker run, do defaults
ENTRYPOINT ["python", "/app/scoring.py"]
CMD ["--year", "2023", "--month", "3"]