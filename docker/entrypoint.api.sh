#!/bin/sh
# A16: apply migrations before serving.
#
# The image already ships alembic.ini and alembic/ (Dockerfile.api copies both),
# but nothing ever invoked them, and the compose healthcheck hit a static
# /health that never touches the database. The result: deploy against an
# unmigrated volume, the container reports healthy, and the first real request
# 500s on a missing table.
#
# This runs migrations then execs uvicorn, so a migration failure exits
# non-zero and the container fails loudly at startup instead of serving 500s
# later. `depends_on: service_healthy` on postgres guarantees the server is up
# before this runs; a genuine ordering problem now surfaces as a failed start
# rather than as intermittent runtime errors.
set -e

echo "==> Applying database migrations"
alembic upgrade head

echo "==> Starting API"
exec "$@"
