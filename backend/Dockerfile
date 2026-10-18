# One container for the public demo: Postgres, the FastAPI backend, and the built Next.js board.
# Data lives inside the container and resets on every restart.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends postgresql && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY schema.sql ./
COPY app ./app
COPY web ./web
COPY start.sh ./

ENV DATABASE_URL=postgresql://ledger:ledger@localhost:5432/ledger \
    DEMO_SEED=serious_earthquake \
    PORT=8000
EXPOSE 8000
CMD ["sh", "/app/start.sh"]
