
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Install production dependencies only (includes gunicorn, excludes pytest/dev tools)
COPY requirements/base.txt requirements/prod.txt /tmp/requirements/
RUN pip install -r /tmp/requirements/prod.txt

# Copy application code — baked into image (no volume mounts in prod)
COPY . .


# OpenShift runs containers with a random UID by default and rejects root.
# Creating a dedicated user ensures the app works under any assigned UID.
RUN addgroup --system --gid 1001 app \
  && adduser --system --uid 1001 --ingroup app --no-create-home app \
  && chown -R app:app /app

RUN chmod +x /app/entrypoint.sh

# Switch to non-root before runtime
USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
