FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command — overridden in docker-compose.yml for beat vs worker
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", \
     "--queues=default,ai,accounting,social,inventory,payroll,reminders,ocr"]
