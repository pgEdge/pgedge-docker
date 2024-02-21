import json
import os
import sys
import time
from typing import Any, Optional, Tuple
import psycopg

SPEC_PATH = [
    "/home/pgedge/db.json",
    "/home/pgedge/node.secret.json",
    "/home/pgedge/node.spec.json",
]


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


def read_spec() -> dict[str, Any]:
    for path in SPEC_PATH:
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


def spock_sub_create(cursor, sub_name: str, other_dsn: str):
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
            cursor.execute(sub_create)
            return
        except Exception as exc:
            info("waiting for subscription to work...", exc)
            time.sleep(2)


def get_admin_creds(secret) -> Tuple[str, str]:
    for user in secret["users"]:
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
    # For backwards compatibility. Remove this once we've launched and
    # switched all databases to use the "hostname" key.
    return node["internal_hostname"]


def main():
    # The spec contains the desired settings
    try:
        spec = read_spec()
    except FileNotFoundError:
        info("ERROR: spec not found, skipping initialization")
        sys.exit(1)

    database = spec.get("name")
    if not database:
        info("ERROR: database name not found in spec")
        sys.exit(1)

    nodes = spec.get("nodes")
    if not nodes:
        info("ERROR: nodes not found in spec")
        sys.exit(1)

    users = spec.get("users")
    if not users:
        info("ERROR: users not found in spec")
        sys.exit(1)

    # Give Postres a moment to start
    time.sleep(3)

    info("initializing database node")

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

    admin_username, admin_password = get_admin_creds(spec)
    if not admin_username or not admin_password:
        info("ERROR: admin user configuration not found in spec")
        sys.exit(1)

    # This DSN will be used for Spock subscriptions
    spock_dsn = dsn(dbname=database, user="pgedge", host=hostname)

    # This DSN will be used for the admin connection
    local_dsn = dsn(dbname=spec["name"], user=admin_username, pw=admin_password)

    # This DSN will be used to the internal admin connection
    internal_dsn = dsn(dbname=spec["name"], user="pgedge", pw=pgedge_pw)

    # Bootstrap users and the primary database by connecting to the "init"
    # database which is built into the Docker image
    init_dbname = os.getenv("INIT_DATABASE")
    init_username = os.getenv("INIT_USERNAME")
    init_password = os.getenv("INIT_PASSWORD")
    init_dsn = dsn(dbname=init_dbname, user=init_username, pw=init_password)
    if not can_connect(init_dsn) and can_connect(local_dsn):
        info("database node already initialized")
        sys.exit(0)
    with connect(init_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"CREATE ROLE pgedge_superuser WITH NOLOGIN;",
                f"GRANT {get_superuser_roles()} TO pgedge_superuser WITH ADMIN true;",
                f"GRANT SET ON PARAMETER {SUPERUSER_PARAMETERS} TO pgedge_superuser;",
            ]
            for user in postgres_users.values():
                stmts.extend(create_user_statement(user))
            stmts += [
                f"CREATE DATABASE {database} OWNER {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {database} TO {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {init_dbname} TO {admin_username};",
                f"GRANT ALL PRIVILEGES ON DATABASE {database} TO pgedge;",
                f"ALTER USER pgedge WITH PASSWORD '{pgedge_pw}' LOGIN SUPERUSER REPLICATION;",
                f"GRANT pgedge TO {admin_username} WITH SET TRUE, INHERIT FALSE;",
            ]
            for statement in stmts:
                cur.execute(statement)

    schemas = ["public", "spock", "pg_catalog", "information_schema"]

    # Drop the init database and user
    with connect(internal_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"DROP DATABASE {init_dbname};",
                f"DROP USER {init_username};",
            ]
            for statement in stmts:
                cur.execute(statement)

    # Further configuration on the primary database
    with connect(internal_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = [
                f"CREATE EXTENSION IF NOT EXISTS spock;",
                f"CREATE EXTENSION IF NOT EXISTS snowflake;",
                f"CREATE EXTENSION IF NOT EXISTS pg_stat_statements;",
            ]
            if "pgcat_auth" in postgres_users:
                # supports auth_query from pgcat
                stmts.append(f"GRANT SELECT ON pg_shadow TO pgcat_auth;")
            for user in postgres_users.values():
                stmts.extend(alter_user_statements(user, database, schemas))
            stmts.append(
                f"SELECT spock.node_create(node_name := '{node_name}', dsn := '{spock_dsn}');"
            )
            for statement in stmts:
                cur.execute(statement)

    with connect(local_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = []
            for user in postgres_users.values():
                stmts.extend(alter_user_statements(user, database, ["public"]))
            for statement in stmts:
                cur.execute(statement)

    with connect(internal_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET log_statement = 'none';")
            stmts = []
            for user in postgres_users.values():
                stmts.extend(alter_user_statements(user, database, schemas))
            for statement in stmts:
                cur.execute(statement)

    info(f"spock node created ({node_name})")

    # Give the other nodes a couple seconds to reach this point as well. The
    # below code will retry but doing this means fewer errored attempts in the
    # log file. Other nodes should be able to connect to us at this point.
    time.sleep(5)

    # Wait for each peer to come online and then subscribe to it
    peers = [node for node in spec["nodes"] if node["name"] != node_name]
    with connect(local_dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            for peer in peers:
                info("waiting for peer:", peer["name"])
                peer_dsn = dsn(
                    dbname=database,
                    user="pgedge",
                    host=get_hostname(peer),
                )
                wait_for_spock_node(peer_dsn)
                spock_sub_create(cur, f"sub_{node_name}{peer['name']}", peer_dsn)
                info("subscribed to peer:", peer["name"])

    info(f"database node initialized ({node_name})")


if __name__ == "__main__":
    main()
