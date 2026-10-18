#!/bin/sh
# Start a local Postgres, create the ledger role and database, then run the API (which applies schema.sql).
set -e
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | head -1)
export PGDATA=/var/lib/postgresql/data
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$PGDATA" && chown -R postgres:postgres /var/lib/postgresql
  su postgres -c "$PGBIN/initdb -D $PGDATA -A trust -U postgres" > /dev/null
fi
su postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-c listen_addresses=localhost' -w start" > /dev/null
su postgres -c "psql -q -c \"DO \\\$\\\$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='ledger') THEN CREATE ROLE ledger LOGIN PASSWORD 'ledger'; END IF; END\\\$\\\$;\""
su postgres -c "psql -q -tc \"SELECT 1 FROM pg_database WHERE datname='ledger'\" | grep -q 1 || createdb -O ledger ledger"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
