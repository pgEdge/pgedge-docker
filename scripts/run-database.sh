#!/bin/bash

set -e

PGV=${PGV:-16}

# Error if PGDATA is not set
if [[ ! -n "${PGDATA}" ]]; then
    echo "**** ERROR: PGDATA must be set ****"
    exit 1
fi

# An initial data directory is included in the base image here. We'll copy
# it to PGDATA and proceed with the PGDATA directory as the real db.
INIT_DATA_DIR=/opt/pgedge/data/pg${PGV}

# Set permissions on PGDATA in a way that will make Postgres happy. Don't fail
# here on error, since Postgres will complain later if there is a problem.
mkdir -p ${PGDATA}
chmod 700 ${PGDATA} || true

# Initialize PGDATA directory if it's empty. Note when the container restarts
# with an existing volume, this copying should NOT occur.
PGCONF="${PGDATA}/postgresql.conf"
if [[ ! -f "${PGCONF}" ]]; then
    IS_SETUP="1"
    echo "**** pgEdge: copying ${INIT_DATA_DIR} to ${PGDATA} ****"
    cp -R -u -p ${INIT_DATA_DIR}/* ${PGDATA}
fi

# Detect the database specification file
if [[ -f "/home/pgedge/db.json" ]]; then
    SPEC_PATH="/home/pgedge/db.json"
fi

NODE_NAME=${NODE_NAME:-n1}

# Initialize users and subscriptions in the background if there was a spec
if [[ -n "${SPEC_PATH}" ]]; then

    if [[ "${IS_SETUP}" = "1" ]]; then
        # Write the database name as cron.database_name in the configuration file
        NAME=$(jq -r ".name" "${SPEC_PATH}")
        echo "**** pgEdge: database name is ${NAME} ****"
        echo "cron.database_name = '${NAME}'" >>${PGCONF}
        SNOWFLAKE_NODE=$(echo ${NODE_NAME} | sed "s/[^0-9]*//g") # n3 -> 3
        echo "snowflake.node = ${SNOWFLAKE_NODE}" >>${PGCONF}
        echo "**** pgEdge: snowflake.node = ${SNOWFLAKE_NODE} ****"
        PGEDGE_AUTODDL=$(jq -r 'any(.options[]?; . == "autoddl:enabled")' ${SPEC_PATH})
        if [[ "${PGEDGE_AUTODDL}" = "true" ]]; then
            echo "spock.enable_ddl_replication = on" >>${PGCONF}
            echo "spock.include_ddl_repset = on" >>${PGCONF}
            echo "spock.allow_ddl_from_functions = on" >>${PGCONF}
            echo "**** pgEdge: autoddl enabled ****"
        fi
    fi

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
    PGV=${PGV} python3 /home/pgedge/scripts/init-database.py &
fi

# Run Postgres in the foreground
echo "**** pgEdge: starting postgres with PGDATA=${PGDATA} ****"
/opt/pgedge/pg${PGV}/bin/postgres -D ${PGDATA} 2>&1
