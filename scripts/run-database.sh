#!/bin/bash

set -e

DEFAULT_SPEC_PATH="/home/pgedge/db.json"
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
SPEC_PATHS=("$@")
if [[ "${#SPEC_PATHS[@]}" -lt 1 && -e "${DEFAULT_SPEC_PATH}" ]]; then
    SPEC_PATHS=("${DEFAULT_SPEC_PATH}")
fi

NODE_NAME=${NODE_NAME:-n1}

# Initialize users and subscriptions in the background if there was a spec
if [[ "${#SPEC_PATHS[@]}" -gt 0 ]]; then
    # Merge spec files together
    MERGED_SPEC=/home/pgedge/.merged-spec.json
    mkdir -p $(dirname "${MERGED_SPEC}")
    jq -s 'reduce .[] as $spec ({}; . * $spec)' "${SPEC_PATHS[@]}" > "${MERGED_SPEC}"

    if [[ "${IS_SETUP}" = "1" ]]; then
        # Write the database name as cron.database_name in the configuration file
        NAME=$(jq -r '.name | select (.!=null)' "${MERGED_SPEC}")
        echo "**** pgEdge: database name is ${NAME} ****"
        echo "cron.database_name = '${NAME}'" >>${PGCONF}
        SNOWFLAKE_NODE=$(echo ${NODE_NAME} | sed "s/[^0-9]*//g") # n3 -> 3
        echo "snowflake.node = ${SNOWFLAKE_NODE}" >>${PGCONF}
        echo "**** pgEdge: snowflake.node = ${SNOWFLAKE_NODE} ****"

        PGEDGE_AUTODDL=$(jq -r 'any(.options[]?; . == "autoddl:enabled")' ${MERGED_SPEC})

        if [[ "${PGEDGE_AUTODDL}" = "true" ]]; then
            echo "spock.enable_ddl_replication = on" >>${PGCONF}
            echo "spock.include_ddl_repset = on" >>${PGCONF}
            echo "spock.allow_ddl_from_functions = on" >>${PGCONF}
            echo "**** pgEdge: autoddl enabled ****"
        fi
    fi

    # Write pgedge password to .pgpass if needed
    if [[ ! -e ~/.pgpass || -z $(awk -F ':' '$4 == "pgedge"' ~/.pgpass) ]]; then
        PGEDGE_PW=$(jq -r '.users[]? |
            select(.username == "pgedge") |
            .password' "${MERGED_SPEC}")

        if [[ -z "${PGEDGE_PW}" ]]; then
            echo "**** ERROR: pgedge user missing from spec ****"
            exit 1
        fi
        echo "*:*:*:pgedge:${PGEDGE_PW}" >>~/.pgpass
        chmod 0600 ~/.pgpass
    fi
        
    MODE=$(jq -r '.mode // "online"' ${MERGED_SPEC})
    if [[ "${MODE}" = "offline" ]]; then
        # Spawn init script in foreground for mode: offline
        echo "**** pgEdge: starting database in mode: offline ****"
        PGV=${PGV} python3 /home/pgedge/scripts/init-database.py "${MERGED_SPEC}" 2>&1
        exit 0
    fi

    # Spawn init script in background for normal operation
    echo "**** pgEdge: starting database in mode: ${MODE} ****"
    PGV=${PGV} python3 /home/pgedge/scripts/init-database.py "${MERGED_SPEC}" &
    # Delay slightly to ensure the init script has time to write any configs
    sleep 2
fi




## SigintHandler
sigint_handler() {
  if [ $pid -ne 0 ]; then
    # the above if statement is important because it ensures
    # that the application has already started. without it you
    # could attempt cleanup steps if the application failed to
    # start, causing errors.
    echo "SIGINT received, beginning graceful shutdown"
    kill -2 "$pid"
    wait "$pid"
  fi
  exit 130; # SIGINT
}

## Setup signal trap
# on callback execute the specified handler
trap 'sigint_handler' SIGINT

# Start postgres in the background
echo "**** pgEdge: starting postgres with PGDATA=${PGDATA} ****"
/opt/pgedge/pg${PGV}/bin/postgres -D ${PGDATA} 2>&1 &

pid="$!"

## Wait forever until postgres dies
wait "$pid"
return_code="$?"

echo "Application exited with return code: $return_code"

# echo the return code of postgres
exit $return_code