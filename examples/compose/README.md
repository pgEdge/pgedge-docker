# How to run this example

```sh
docker compose up -d
```

# How to interact with this example

This configuration creates a database called `example_db` that's replicated between two pgEdge nodes.

## Connect to `example_db` with Docker

To open a `psql` session on the first node, run:
```sh
docker compose exec postgres-n1 psql -U admin example_db
```

Likewise, to open a `psql` session on the second node, run:
```sh
docker compose exec postgres-n2 psql -U admin example_db
```

## Try out replication

1. Create a table on the first node:
```sh
docker compose exec postgres-n1 psql -U admin example_db -c "create table example (id int primary key, data text);"
```
2. Insert a row into our new table on the second node:
```sh
docker compose exec postgres-n2 psql -U admin example_db -c "insert into example (id, data) values (1, 'Hello, pgEdge!');"
```
3. See that the new row has replicated back to the first node:
```sh
docker compose exec postgres-n1 psql -U admin example_db -c "select * from example;"
```

## Load the Northwind example dataset

The Northwind example dataset is a PostgreSQL database dump that you can use to try replication with a more realistic database.  To load the Northwind dataset into your pgEdge database, run:

```sh
curl https://downloads.pgedge.com/platform/examples/northwind/northwind.sql | docker compose exec -T postgres-n1 psql -U admin example_db
```

Now, try querying one of the new tables from the other node:

```sh
docker compose exec postgres-n2 psql -U admin example_db -c "select * from northwind.shippers"
```

## Connect to `example_db` from another client

If you have `psql`, pgAdmin, or another client installed on your host machine, you can use these connection strings to connect to each node:

- First node: `host=localhost port=6432 user=admin password=password dbname=example_db`
- Second node: `host=localhost port=6433 user=admin password=password dbname=example_db`

For example, using `psql`:

```sh
psql 'host=localhost port=6432 user=admin password=password dbname=example_db'
```

# How to modify this example

The `docker-compose.yaml` file contains a JSON-formatted section at the top that configures the
pgEdge containers. The top-level sections are:
- `name`: Sets the name of the database.
- `options`: Used to enable optional pgEdge features.
- `nodes`: Configures the pgEdge nodes.
- `users`: Configures which users will be created on each pgEdge node.
  - The `admin` and `pgedge` users are required.
  - You can customize the `admin` and `pgedge` passwords by setting the `PGEDGE_PASSWORD` and `ADMIN_PASSWORD` environment variables the first time you start the example, e.g.:

```sh
ADMIN_PASSWORD='different password' docker compose up -d
```

Note that this configuration only takes effect when the containers are first created. To recreate the database with a new configuration, stop the running example:

```sh
docker compose down
```

And start it again:

```sh
docker compose up -d
```
