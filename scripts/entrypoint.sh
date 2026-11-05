#!/bin/sh
set -eu
umask 077
if [ "${CONSOLE_DEPLOYMENT_PREFLIGHT:-false}" = true ]; then
    python -m app.console_deployment preflight
fi
alembic upgrade head
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 80 --workers 1 --no-proxy-headers
