#!/bin/sh
set -eu
umask 077
alembic upgrade head
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 80 --workers 1 --no-proxy-headers
