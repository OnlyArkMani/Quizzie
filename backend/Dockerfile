FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Workers configurable via env — default 4 for prod, override per host
# Formula: (2 x CPU cores) + 1
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-4}
