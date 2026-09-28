FROM ghcr.io/typst/typst:0.15.1 AS typst
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 TZ=America/Sao_Paulo HOME=/home/athlete
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core tzdata && rm -rf /var/lib/apt/lists/*
COPY --from=typst /bin/typst /usr/local/bin/typst
WORKDIR /app
COPY dashboard/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt fitdecode==0.11.0 pypdf==6.9.0 mcp-garmin==0.3.0
COPY scripts /app/scripts
COPY dashboard /app/dashboard
RUN useradd --create-home --uid 1000 athlete && mkdir -p /app/data /app/analysis/context /app/runtime/dashboard /app/activities/notes/medical && chown -R athlete:athlete /app
USER athlete
EXPOSE 8788
CMD ["python", "-m", "uvicorn", "dashboard.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8788", "--no-access-log"]
