#!/bin/sh
set -eu

read_secret() {
  name="$1"
  path="/run/secrets/${name}"
  if [ ! -s "${path}" ]; then
    printf '%s\n' "CONFIG_GENERATED_SECRET_MISSING: ${name}" >&2
    exit 2
  fi
  cat "${path}"
}

postgres_password="$(read_secret postgres_password)"
export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${postgres_password}@postgres:5432/${POSTGRES_DB}"
export MIGRATION_DATABASE_URL="${DATABASE_URL}"
export JWT_SECRET_KEY="$(read_secret jwt_secret_key)"
export JIRA_TOKEN_ENCRYPTION_KEY="$(read_secret jira_token_encryption_key)"
unset postgres_password

if [ "$(id -u)" -eq 0 ]; then
  exec su-exec cloudops "$@"
fi

exec "$@"
