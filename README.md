# pgEdge Docker Swarm Example

This example shows how to run a pgEdge cluster in Docker Swarm as a stack.

## Setup

This example runs on both MacOS and Linux. You'll need a local swarm initialized:

```
docker swarm init
```

## Usage

In this directory, run:

```
docker stack deploy -c ./stack.yaml db
```

That deploys a stack named `db` with the services defined in `stack.yaml`. The
stack runs two virtual pgEdge "nodes" named `n1` and `n2`. There are pgCat and
Postgres containers for each node.

## Connectivity

The Traefik load balancer is configured to listen on ports 8080 and 5432. Access
the Traefik dashboard once this is running at the following URL in your browser:

```
http://localhost:8080/dashboard
```

Using the `traefik.*` deploy labels on the pgcat containers, we tell Traefik
to route `postgres` traffic to pgcat. Consequently, if you use `psql` to connect
to localhost port 5432, you'll connect to one of the postgres containers _through_
Traefik and pgcat.

psql -> traefik -> pgcat -> postgres

You can bypass Traefik and connect with `psql` directly to pgcat or postgres at
the following ports:

- pgcat-n1: 6432
- postgres-n1: 6431
- pgcat-n2: 6442
- postgres-n2: 6441

You can see how the ports are exposed in the `stack.yaml` file.

## Example Psql Commands

Here's an example:

```
PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX PGSSLMODE=require psql -h localhost -p 5432 -U admin defaultdb
```

Note the password is configured in the `db.json` file.

You can also reference the [Makefile](./Makefile) for some commands.

## Notes

Traefik _can_ be deployed in a separate stack. It monitors for containers to proxy
to using the Docker API.

If you want to experiment with different `HostSNI` values in the Traefik
configuration, you can change the `HostSNI` value in the `stack.yaml` file on
the `pgcat` service. A trick for testing this on localhost is to add an entry
to your `/etc/hosts` file e.g:

```
127.0.0.1 n1
127.0.0.1 n2
```

Then you can use those hostnames to connect to the nodes, e.g.

```
PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX PGSSLMODE=require psql -h n1 -p 5432 -U admin defaultdb
```
