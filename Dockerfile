FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY mlruns ./mlruns

RUN pip install --upgrade pip && pip install -e ".[ml]" && rm -f /app/README.md && rm -rf /app/src/energy_demand_forecast.egg-info /root/.cache/pip

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
