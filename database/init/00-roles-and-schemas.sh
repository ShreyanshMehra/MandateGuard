#!/bin/bash
# Creates the broker and bank service roles and schemas described in
# docs/ARCHITECTURE.md. Tables are added in Milestone 3; this script only
# establishes the trust boundary between the two schemas.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE mandateguard_broker LOGIN PASSWORD '${BROKER_DB_PASSWORD}';
    CREATE ROLE mandateguard_bank LOGIN PASSWORD '${BANK_DB_PASSWORD}';

    CREATE SCHEMA IF NOT EXISTS broker AUTHORIZATION mandateguard_broker;
    CREATE SCHEMA IF NOT EXISTS bank AUTHORIZATION mandateguard_bank;

    REVOKE ALL ON SCHEMA bank FROM mandateguard_broker;
    REVOKE ALL ON SCHEMA broker FROM mandateguard_bank;
    REVOKE ALL ON SCHEMA bank FROM PUBLIC;
    REVOKE ALL ON SCHEMA broker FROM PUBLIC;

    ALTER ROLE mandateguard_broker SET search_path = broker;
    ALTER ROLE mandateguard_bank SET search_path = bank;
EOSQL
