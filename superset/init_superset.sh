#!/usr/bin/env bash

set -euo pipefail

: "${SUPERSET_ADMIN_USERNAME:?Missing SUPERSET_ADMIN_USERNAME}"
: "${SUPERSET_ADMIN_PASSWORD:?Missing SUPERSET_ADMIN_PASSWORD}"
: "${SUPERSET_ADMIN_EMAIL:?Missing SUPERSET_ADMIN_EMAIL}"

superset db upgrade

if superset fab list-users | grep --fixed-strings --quiet "${SUPERSET_ADMIN_USERNAME}"; then
    printf 'Superset administrator already exists: %s\n' \
        "${SUPERSET_ADMIN_USERNAME}"
else
    superset fab create-admin \
        --username "${SUPERSET_ADMIN_USERNAME}" \
        --firstname "${SUPERSET_ADMIN_FIRST_NAME:-Local}" \
        --lastname "${SUPERSET_ADMIN_LAST_NAME:-Admin}" \
        --email "${SUPERSET_ADMIN_EMAIL}" \
        --password "${SUPERSET_ADMIN_PASSWORD}"
fi

superset init
