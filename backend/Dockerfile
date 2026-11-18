FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# WeasyPrint system libraries (PDF business plans). Remove these and the pip line to slim the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt && pip install "weasyprint>=62"

COPY . .

EXPOSE 8000
# Render (and most hosts) inject $PORT. One uvicorn worker (the default): the Telegram listener, the bot and the
# in-process caches must exist exactly once. Migrations run on startup (AUTO_MIGRATE=true).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
