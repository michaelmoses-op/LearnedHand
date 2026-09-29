#!/usr/bin/env bash
# Idempotently create roles, databases and extensions for local dev/test.
#
# Admin access (first that applies):
#   PGADMIN_URL=postgresql://user:pass@host:5432/postgres   -> psql "$PGADMIN_URL"
#   otherwise: sudo -u postgres psql   (default on Ubuntu/WSL2)
#
# Passwords are dev-only defaults; override with APP_OWNER_PASSWORD / APP_USER_PASSWORD.
set -euo pipefail

OWNER_PW="${APP_OWNER_PASSWORD:-app_owner_dev}"
USER_PW="${APP_USER_PASSWORD:-app_user_dev}"
DBS=(app_dev app_test)
HOST="${PGHOST_APP:-localhost}"
PORT="${PGPORT_APP:-5432}"

# usage: admin <database> [psql args...]
admin() {
  local db="$1"; shift
  if [[ -n "${PGADMIN_URL:-}" ]]; then
    psql "${PGADMIN_URL%/*}/${db}" -v ON_ERROR_STOP=1 -X -q "$@"
  else
    sudo -u postgres psql -d "$db" -v ON_ERROR_STOP=1 -X -q "$@"
  fi
}

fail() { echo "ERROR: $*" >&2; echo "See docs/LOCAL_SETUP.md (Troubleshooting)." >&2; exit 1; }

admin postgres -c "select 1" >/dev/null 2>&1 \
  || fail "Cannot connect to PostgreSQL as an admin. Is the server running (pg_lsclusters)? Set PGADMIN_URL or allow 'sudo -u postgres'."

avail=$(admin postgres -tAc "select count(*) from pg_available_extensions where name='vector'")
[[ "$avail" == "1" ]] || fail "pgvector is not installed. Ubuntu: sudo apt install postgresql-16-pgvector"

# Roles (passwords are set on every run so the script converges).
admin postgres <<SQL
do \$\$
begin
  if not exists (select from pg_roles where rolname = 'app_owner') then
    create role app_owner login createdb;
  end if;
  if not exists (select from pg_roles where rolname = 'app_user') then
    create role app_user login nosuperuser nocreatedb nocreaterole noinherit;
  end if;
end \$\$;
alter role app_owner password '${OWNER_PW}';
alter role app_user  password '${USER_PW}';
SQL

for db in "${DBS[@]}"; do
  exists=$(admin postgres -tAc "select 1 from pg_database where datname='${db}'")
  if [[ "$exists" != "1" ]]; then
    admin postgres -c "create database ${db} owner app_owner"
  fi
  admin "$db" <<SQL
set client_min_messages = warning;
create extension if not exists vector;
create extension if not exists pg_trgm;
grant connect on database ${db} to app_user;
grant usage on schema public to app_user;
alter default privileges for role app_owner in schema public
  grant select, insert, update, delete on tables to app_user;
alter default privileges for role app_owner in schema public
  grant usage, select on sequences to app_user;
SQL
done

cat <<EOF

Database setup complete. Put these in .env:

DATABASE_URL=postgresql+asyncpg://app_user:${USER_PW}@${HOST}:${PORT}/app_dev
MIGRATION_DATABASE_URL=postgresql+asyncpg://app_owner:${OWNER_PW}@${HOST}:${PORT}/app_dev
TEST_DATABASE_URL=postgresql+asyncpg://app_user:${USER_PW}@${HOST}:${PORT}/app_test
TEST_MIGRATION_DATABASE_URL=postgresql+asyncpg://app_owner:${OWNER_PW}@${HOST}:${PORT}/app_test
EOF
