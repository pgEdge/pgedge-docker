#!/bin/bash

set -e

PG_VERSION=${PG_VERSION:-16}
PG_BINARY=/opt/pgedge/pg${PG_VERSION}/bin/postgres

DEFAULT_DATA_DIR=/opt/pgedge/data/pg${PG_VERSION}
PGDATA=${PGDATA:-${DEFAULT_DATA_DIR}}

# Copy preexisting data directory if the data directory was customized
# and its currently empty
if [[ "${PGDATA}" != "${DEFAULT_DATA_DIR}" ]]; then
    mkdir -p ${PGDATA}
    chmod 700 ${PGDATA} || true
    # Use postgresql.conf as a marker to decide if the data dir is empty
    if [[ -f "${PGDATA}/postgresql.conf" ]]; then
        echo "**** pgEdge: ${PGDATA} is not empty, skipping copy ****"
    else
        echo "**** pgEdge: copying ${DEFAULT_DATA_DIR} to ${PGDATA} ****"
        cp -R ${DEFAULT_DATA_DIR}/* ${PGDATA}
    fi
fi

# Locate the database specification file
if [[ -f "/home/pgedge/db.json" ]]; then
    SPEC_PATH="/home/pgedge/db.json"
fi

# Initialize users and subscriptions in the background if there was a spec
if [[ -n "${SPEC_PATH}" ]]; then

    # Write the database name as cron.database_name in the configuration file
    NAME=$(jq -r ".name" "${SPEC_PATH}")
    echo "**** pgEdge: database name is ${NAME} ****"
    PG_CONF=/opt/pgedge/data/pg${PG_VERSION}/postgresql.conf
    echo "cron.database_name = '${NAME}'" >>${PG_CONF}

    # Write pgedge password to .pgpass if needed
    if [[ ! -e ~/.pgpass || -z $(awk -F ':' '$4 == "pgedge"' ~/.pgpass) ]]; then
        PGEDGE_PW=$(jq -r '.users[] |
            select(.username == "pgedge") |
            .password' ${SPEC_PATH})

        if [[ -z "${PGEDGE_PW}" ]]; then
            echo "**** ERROR: pgedge user missing from spec ****"
            exit 1
        fi
        echo "*:*:*:pgedge:${PGEDGE_PW}" >>~/.pgpass
        chmod 0600 ~/.pgpass
    fi

    # Spawn init script which creates users and subscriptions
    echo "**** pgEdge: starting init script in background ****"
    PG_VERSION=${PG_VERSION} python3 /home/pgedge/scripts/init-database.py &

else
    echo "**** WARNING: no pgEdge node spec found ****"
    # If REQUIRE_SPEC is set, exit
    if [[ -n "${REQUIRE_SPEC}" ]]; then
        exit 1
    fi
fi

# Run Postgres in the foreground
echo "**** pgEdge: starting postgres with data directory ${PGDATA} ****"
${PG_BINARY} -D ${PGDATA} 2>&1
