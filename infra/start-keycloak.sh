#!/bin/bash
set -eu
export KC_BOOTSTRAP_ADMIN_PASSWORD="$(cat /run/secrets/kc_admin)"
export KC_DB_PASSWORD="$(cat /run/secrets/kc_db)"
exec /opt/keycloak/bin/kc.sh start-dev --import-realm
