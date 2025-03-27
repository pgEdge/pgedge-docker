from dataclasses import dataclass
import json
import os
import sys
import time
from typing import Any, Optional, Tuple
import psycopg

PG_CONF_FILE = "/data/pgdata/postgresql.conf"


SUPERUSER_PARAMETERS = ", ".join(
    [
        "commit_delay",
        "deadlock_timeout",
        "lc_messages",
        "log_duration",
        "log_error_verbosity",
        "log_executor_stats",
        "log_lock_waits",
        "log_min_duration_sample",
        "log_min_duration_statement",
        "log_min_error_statement",
        "log_min_messages",
        "log_parser_stats",
        "log_planner_stats",
        "log_replication_commands",
        "log_statement",
        "log_statement_sample_rate",
        "log_statement_stats",
        "log_temp_files",
        "log_transaction_sample_rate",
        "pg_stat_statements.track",
        "pg_stat_statements.track_planning",
        "pg_stat_statements.track_utility",
        "session_replication_role",
        "temp_file_limit",
        "track_activities",
        "track_counts",
        "track_functions",
        "track_io_timing",
    ]
)


def read_spec(path: str) -> dict[str, Any]:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    raise FileNotFoundError("spec not found")


def info(*args):
    print("**** pgEdge:", *args, "****")
    sys.stdout.flush()


def connect(dsn: str, autocommit: bool = True):
    while True:
        try:
            return psycopg.connect(dsn, autocommit=autocommit)
        except psycopg.OperationalError as exc:
            info("unable to connect to database, retrying in 2 sec...", exc)
            time.sleep(2)


def can_connect(dsn: str) -> bool:
    try:
        psycopg.connect(dsn, connect_timeout=5)
        return True
    except psycopg.OperationalError:
        return False


def dsn(
    dbname: str,
    user: str,
    pw: Optional[str] = None,
    host: str = "localhost",
    port: int = 5432,
) -> str:
    fields = [
        f"host={host}",
        f"dbname={dbname}",
        f"user={user}",
        f"port={port}",
    ]
    if pw:
        fields.append(f"password={pw}")

    return " ".join(fields)


def wait_for_spock_node(dsn: str):
    with connect(dsn) as conn:
        with conn.cursor() as cursor:
            while True:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM spock.node;")
                    row = cursor.fetchone()
                    if row[0] > 0:
                        return
                except Exception as exc:
                    info("peer spock.node not configured, retrying in 2 sec...", exc)
                    time.sleep(2)


def spock_sub_create(conn, sub_name: str, other_dsn: str):
    forward_origins = "{}"
    replication_sets = "{default, default_insert_only, ddl_sql}"
    sub_create = f"""
    SELECT spock.sub_create(
        subscription_name := '{sub_name}',
        provider_dsn := '{other_dsn}',
        replication_sets := '{replication_sets}',
        forward_origins := '{forward_origins}',
        synchronize_structure := 'false',
        synchronize_data := 'false',
        apply_delay := '0'
    );"""
    # Retry until it works
    while True:
        try:
            with conn.cursor() as cursor:
                cursor.execute(sub_create)
            return
        except Exception as exc:
            info("waiting for subscription to work...", exc)
            time.sleep(2)

def spock_sub_drop(cursor, sub_name: str):
    sub_drop_if_exists = f"""
    SELECT spock.sub_drop(
        subscription_name := '{sub_name}',
        ifexists := 'true'
    );"""

    # Retry until it works
    while True:
        try:
            cursor.execute(sub_drop_if_exists)
            return
        except Exception as exc:
            info("waiting for subscription to drop...", exc)
            time.sleep(2)


def get_admin_creds(postgres_users: dict[str, Any]) -> Tuple[str, str]:
    for _, user in postgres_users.items():
        if user.get("service") == "postgres" and user["type"] == "admin":
            return user["username"], user["password"]
    return "", ""


def get_superuser_roles() -> str:
    pg_version = os.getenv("PGV")
    if pg_version == "15":
        return ", ".join(
            [
                "pg_read_all_data",
                "pg_write_all_data",
                "pg_read_all_settings",
                "pg_read_all_stats",
                "pg_stat_scan_tables",
                "pg_monitor",
                "pg_signal_backend",
                "pg_checkpoint",
            ]
        )
    elif pg_version == "16":
        return ", ".join(
            [
                "pg_read_all_data",
                "pg_write_all_data",
                "pg_read_all_settings",
                "pg_read_all_stats",
                "pg_stat_scan_tables",
                "pg_monitor",
                "pg_signal_backend",
                "pg_checkpoint",
                "pg_use_reserved_connections",
                "pg_create_subscription",
            ]
        )
    else:
        raise ValueError(f"unrecognized postgres version: '{pg_version}'")


def create_user_statement(user) -> list[str]:
    username = user["username"]
    password = user["password"]
    superuser = user.get("superuser")
    user_type = user.get("type")

    if superuser:
        return [f"CREATE USER {username} WITH LOGIN SUPERUSER PASSWORD '{password}';"]
    elif user_type in ["admin", "internal_admin"]:
        return [
            f"CREATE USER {username} WITH LOGIN CREATEROLE CREATEDB PASSWORD '{password}';",
            f"GRANT pgedge_superuser to {username} WITH ADMIN TRUE;",
        ]
    else:
        return [f"CREATE USER {username} WITH LOGIN PASSWORD '{password}';"]


def alter_user_statements(user, dbname: str, schemas: list[str]) -> list[str]:
    name = user["username"]
    stmts = [f"GRANT CONNECT ON DATABASE {dbname} TO {name};"]
    if user["type"] in ["application_read_only", "internal_read_only", "pooler_auth"]:
        for schema in schemas:
            stmts += [
                f"GRANT USAGE ON SCHEMA {schema} TO {name};",
                f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {name};",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {name};",
            ]
        if user["type"] == "internal_read_only":
            stmts.append(f"GRANT EXECUTE ON FUNCTION pg_ls_waldir TO {name};")
            stmts.append(f"GRANT pg_read_all_stats TO {name};")
        return stmts
    else:
        for schema in schemas:
            stmts += [
                f"GRANT USAGE, CREATE ON SCHEMA {schema} TO {name};",
                f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} TO {name};",
                f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} TO {name};",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL PRIVILEGES ON TABLES TO {name};",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL PRIVILEGES ON SEQUENCES TO {name};",
            ]
        return stmts


def get_self_node(spec):
    nodes = spec["nodes"]
    # Use the self entry from the spec if there is one
    if "self" in spec:
        return spec["self"]
    node_name = os.getenv("NODE_NAME", "n1")
    # Find the node with that name
    self_node = next((node for node in nodes if node["name"] == node_name), None)
    if not self_node:
        info(f"ERROR: node {node_name} not found in spec")
        sys.exit(1)
    return self_node


def get_hostname(node: dict) -> str:
    if "hostname" in node:
        return node["hostname"]
    # For backwards compatibility.
    return node["internal_hostname"]


@dataclass
class DatabaseInfo:
    database_name: str
    database_id: str
    hostname: str
    mode: Optional[str]
    nodes: list[dict[str, Any]]
    node_name: str
    postgres_users: dict[str, Any]
    spock_dsn: str
    local_dsn: str
    internal_dsn: str
    init_dsn: str
    init_username: str
    init_dbname: str
    pgedge_pw: str


def get_db_info(spec) -> DatabaseInfo:
    database_name = spec.get("name")
    if not database_name:
        info("ERROR: database name not found in spec")
        sys.exit(1)

    database_id = spec.get("id", "default")

    nodes = spec.get("nodes")
    if not nodes:
        info("ERROR: nodes not found in spec")
        sys.exit(1)

    users = spec.get("users")
    if not users:
        info("ERROR: users not found in spec")
        sys.exit(1)

    # Extract details of this node from the spec
    self_node = get_self_node(spec)
    hostname = get_hostname(self_node)
    node_name = self_node["name"]
    postgres_users = dict(
        (user["username"], user) for user in users if user["service"] == "postgres"
    )

    # Get the pgedge password and remove the user from the dict.
    # This user already exists so we don't need to create it later.
    pgedge_pw = postgres_users.pop("pgedge", {}).get(
        "password", os.getenv("INIT_PASSWORD")
    )
    if not pgedge_pw:
        info("ERROR: pgedge user configuration not found in spec")
        sys.exit(1)
    admin_username, admin_password = get_admin_creds(postgres_users)
    if not admin_username or not admin_password:
        info("ERROR: admin user configuration not found in spec")
        sys.exit(1)

    # This DSN will be used for Spock subscriptions
    spock_dsn = dsn(dbname=database_name, user="pgedge", host=hostname)

    # This DSN will be used for the admin connection
    local_dsn = dsn(dbname=database_name, user=admin_username, pw=admin_password)

    # This DSN will be used to the internal admin connection
    internal_dsn = dsn(dbname=database_name, user="pgedge", pw=pgedge_pw)

    init_dbname = os.getenv("INIT_DATABASE")
    init_username = os.getenv("INIT_USERNAME")
    init_password = os.getenv("INIT_PASSWORD")
    init_dsn = dsn(dbname=init_dbname, user=init_username, pw=init_password)

    return DatabaseInfo(
        database_name=database_name,
        database_id=database_id,
        nodes=nodes,
        hostname=hostname,
        node_name=node_name,
        postgres_users=postgres_users,
        spock_dsn=spock_dsn,
        local_dsn=local_dsn,
        internal_dsn=internal_dsn,
        init_dsn=init_dsn,
        init_dbname=init_dbname,
        init_username=init_username,
        pgedge_pw=pgedge_pw,
        mode=spec.get("mode", "online"),
    )

def init_online_mode(db_info):
    # Give Postgres a moment to start
    time.sleep(3)

    initialized = not can_connect(db_info.init_dsn) and can_connect(db_info.local_dsn)

    if initialized:
        info("database node already initialized")
    else:
        info("initializing database node")
        init_database(db_info)


def init_offline_mode():
    info("mode offline configured, postgres will not start")
    while True:
        time.sleep(1)


def init_database(db_info: DatabaseInfo):
    admin_username = get_admin_creds(db_info.postgres_users)[0]

    # Bootstrap users and the primary database by connecting to the "init"
    # database which is built into the Docker image
    with connect(db_info.init_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"CREATE ROLE pgedge_superuser WITH NOLOGIN;",
                f"GRANT {get_superuser_roles()} TO pgedge_superuser WITH ADMIN true;",
                f"GRANT SET ON PARAMETER {SUPERUSER_PARAMETERS} TO pgedge_superuser;",
            ]
            for user in db_info.postgres_users.values():
                stmts.extend(create_user_statement(user))
            stmts += [
                f"CREATE DATABASE {db_info.database_name} OWNER {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {db_info.database_name} TO {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {db_info.init_dbname} TO {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {db_info.database_name} TO pgedge;",
                f"ALTER USER pgedge WITH PASSWORD '{db_info.pgedge_pw}' LOGIN SUPERUSER REPLICATION;",
            ]
            for statement in stmts:
                cur.execute(statement)

    info("successfully bootstrapped database users")

    # Drop the init database and user
    with connect(db_info.internal_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"DROP DATABASE {db_info.init_dbname};",
                f"DROP USER {db_info.init_username};",
            ]
            for statement in stmts:
                cur.execute(statement)

    info("successfully dropped init database")

    schemas = ["public", "spock", "pg_catalog", "information_schema"]

    init_spock_node(db_info, schemas)

    # Give the other nodes a couple seconds to reach this point as well. The
    # below code will retry but doing this means fewer errored attempts in the
    # log file. Other nodes should be able to connect to us at this point.
    time.sleep(5)

    # Wait for each peer to come online and then subscribe to it
    init_peer_spock_subscriptions(db_info)

    info(f"database node initialized ({db_info.node_name})")


def init_peer_spock_subscriptions(db_info: DatabaseInfo, drop_existing: bool = False):
    peers = [node for node in db_info.nodes if node["name"] != db_info.node_name]
    with connect(db_info.local_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            for peer in peers:
                info("waiting for peer:", peer["name"])
                peer_dsn = dsn(
                    dbname=db_info.database_name,
                    user="pgedge",
                    host=get_hostname(peer),
                )
                sub_name = f"sub_{db_info.node_name}{peer['name']}".replace("-", "_")
                wait_for_spock_node(peer_dsn)
                if drop_existing:
                    spock_sub_drop(cur, sub_name)
                spock_sub_create(
                    cur, sub_name, peer_dsn
                )
                info("subscribed to peer:", peer["name"])

def init_spock_node(db_info: DatabaseInfo, schemas: list[str]):

    with connect(db_info.internal_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"CREATE EXTENSION IF NOT EXISTS spock;",
                f"CREATE EXTENSION IF NOT EXISTS snowflake;",
                f"CREATE EXTENSION IF NOT EXISTS pg_stat_statements;",
            ]
            if "pgcat_auth" in db_info.postgres_users:
                # supports auth_query from pgcat
                stmts.append(f"GRANT SELECT ON pg_shadow TO pgcat_auth;")
            for user in db_info.postgres_users.values():
                stmts.extend(
                    alter_user_statements(user, db_info.database_name, schemas)
                )
            stmts.append(
                f"SELECT spock.node_create(node_name := '{db_info.node_name}', dsn := '{db_info.spock_dsn}') WHERE '{db_info.node_name}' NOT IN (SELECT node_name FROM spock.node);"
            )
            for statement in stmts:
                cur.execute(statement)

    with connect(db_info.local_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = []
            for user in db_info.postgres_users.values():
                stmts.extend(
                    alter_user_statements(user, db_info.database_name, ["public"])
                )
            for statement in stmts:
                cur.execute(statement)

    with connect(db_info.internal_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = []
            for user in db_info.postgres_users.values():
                stmts.extend(
                    alter_user_statements(user, db_info.database_name, schemas)
                )
            for statement in stmts:
                cur.execute(statement)


def main():
    # The spec contains the desired settings
    try:
        spec = read_spec(sys.argv[1])
    except FileNotFoundError:
        info("ERROR: spec not found, skipping initialization")
        sys.exit(1)

    # Parse the spec so we can pass it around
    db_info = get_db_info(spec)

    if db_info.mode == "offline":
        init_offline_mode()
    else:
        init_online_mode(db_info)


if __name__ == "__main__":
    main()
