#!/usr/bin/env bash
set -euo pipefail

########################################
# Config (override via env if needed)
########################################

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rag-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ragdb}"
POSTGRES_USER="${POSTGRES_USER:-raguser}"

WEAVIATE_HOST="${WEAVIATE_HOST:-localhost}"
WEAVIATE_PORT="${WEAVIATE_PORT:-8080}"
WEAVIATE_CLASS="${WEAVIATE_CLASS:-AccessControlPolicy}"

# If set to "true" -> also drop the class schema in Weaviate
DROP_WEAVIATE_CLASS="${DROP_WEAVIATE_CLASS:-false}"

########################################
# Helpers
########################################

log()  { echo "[cleanup] $*"; }
warn() { echo "[cleanup][WARN] $*" >&2; }
err()  { echo "[cleanup][ERROR] $*" >&2; }

########################################
# 1) Clean Postgres table
########################################

log "Cleaning Postgres table: policy_chunks (container=${POSTGRES_CONTAINER})"

if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
  err "Postgres container '${POSTGRES_CONTAINER}' not running. Aborting."
  exit 1
fi

docker exec -i "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" <<'SQL' 2>/tmp/cleanup_pg_err.log || {
  # if table doesn't exist, just warn
  if grep -q "relation \"policy_chunks\" does not exist" /tmp/cleanup_pg_err.log; then
    warn "Table 'policy_chunks' does not exist, skipping TRUNCATE."
  else
    err "Postgres error while truncating policy_chunks:"
    cat /tmp/cleanup_pg_err.log >&2
    exit 1
  fi
}
TRUNCATE TABLE policy_chunks RESTART IDENTITY CASCADE;
SQL

log "Postgres: policy_chunks truncated successfully."

########################################
# 2) Clean Weaviate objects
########################################

log "Cleaning Weaviate objects for class: ${WEAVIATE_CLASS}"

HTTP_CODE=$(curl -s -o /tmp/cleanup_weaviate_resp.log -w "%{http_code}" \
  -X DELETE "http://${WEAVIATE_HOST}:${WEAVIATE_PORT}/v1/objects?class=${WEAVIATE_CLASS}" || true)

if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "204" ]; then
  log "Weaviate: all objects for class '${WEAVIATE_CLASS}' deleted."
else
  warn "Weaviate DELETE objects returned HTTP ${HTTP_CODE}."
  warn "Response:"
  cat /tmp/cleanup_weaviate_resp.log >&2
fi

########################################
# 3) Optional: Drop Weaviate class
########################################

if [ "${DROP_WEAVIATE_CLASS}" = "true" ]; then
  log "Dropping Weaviate class schema: ${WEAVIATE_CLASS}"

  HTTP_CODE_SCHEMA=$(curl -s -o /tmp/cleanup_weaviate_schema.log -w "%{http_code}" \
    -X DELETE "http://${WEAVIATE_HOST}:${WEAVIATE_PORT}/v1/schema/${WEAVIATE_CLASS}" || true)

  if [ "${HTTP_CODE_SCHEMA}" = "200" ] || [ "${HTTP_CODE_SCHEMA}" = "204" ]; then
    log "Weaviate: class '${WEAVIATE_CLASS}' schema dropped."
  else
    warn "Weaviate DELETE schema returned HTTP ${HTTP_CODE_SCHEMA}."
    warn "Response:"
    cat /tmp/cleanup_weaviate_schema.log >&2
  fi
else
  log "DROP_WEAVIATE_CLASS=false → keeping Weaviate class schema."
fi

log "✅ Cleanup completed."