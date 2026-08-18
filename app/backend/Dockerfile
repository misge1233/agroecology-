FROM python:3.12-slim

WORKDIR /srv

# build-essential kept as a safety net for any source builds; most wheels are prebuilt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Canonical engine + small ML artifacts + dataset + zone lookup are baked in.
# The large GeoTIFF stack (backend/layers/, ~730 MB) is excluded via .dockerignore
# and mounted read-only at /srv/layers by docker-compose (see docker-compose.yml).
COPY recommend.py advisor_agent.py groq_agent.py aez_belt_lookup.csv ./
COPY artifacts ./artifacts
COPY dataset ./dataset
COPY app ./app

# recommend.py resolves its data paths relative to /srv; /srv must be importable.
ENV PYTHONPATH=/srv
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Startup validates that model + dataset + all layers exist (fail-fast).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
