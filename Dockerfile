# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY sample_data.json ./

RUN useradd --create-home appuser \
    && mkdir -p /data /logs \
    && chown -R appuser:appuser /app /data /logs

USER appuser

VOLUME ["/data", "/logs"]
EXPOSE 19892

CMD ["python", "-m", "app.main"]
