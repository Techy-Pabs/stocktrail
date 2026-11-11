#!/bin/sh
# Production start command: apply migrations, then start the API.
# set -e stops the script (and the container) if any command fails,
# so the API never starts against a database that failed to migrate.
set -e

alembic upgrade head

# exec replaces this shell with uvicorn, so it receives stop signals directly.
# Hosts like Render set PORT; locally it defaults to 8000.
# --no-proxy-headers: don't trust X-Forwarded-For from whoever connects, so a
# client can't choose the address the API sees.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers
