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

That deploys a stack named `db` with the services defined in `stack.yaml`.

## Connectivity

Traefik is configured to listen on ports 8080 and 5432. Access the Traefik
dashboard once this is running at the following URL in your browser:

```
http://localhost:8080/dashboard
```

Using the `traefik.*` deploy labels on the pgcat container, we tell Traefik
to route `postgres` traffic to pgcat. Consequently, if you use `psql` to connect
to localhost port 5432, you'll connect to the postgres container _through_
Traefik and pgcat.

psql -> traefik -> pgcat -> postgres

You can bypass Traefik and connect with `psql` directly to pgcat or postgres at
the following ports:

- pgcat: 6432
- postgres: 6431

You can see how the ports are exposed in the `stack.yaml` file.

## Example Psql Commands

Here's an example:

```
PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX PGSSLMODE=require psql -h localhost -p 5432 -U admin defaultdb
```

Note the password is configured in the `db.json` file.

You can also reference the [Makefile](./Makefile) for some commands.

## Notes

Traefik can be deployed in a separate stack. It monitors for containers to proxy
to using the Docker API.

If you want to experiment with different `HostSNI` values in the Traefik
configuration, you can change the `HostSNI` value in the `stack.yaml` file on
the `pgcat` service. A trick for testing this on localhost is to add an entry
to your `/etc/hosts` file e.g:

```
127.0.0.1 foo.bar.pgedge.io
```

Then you can use that hostname to route to potentially one of multiple pgcat
services running in Docker:

```
- "traefik.tcp.routers.router-db-123.rule=HostSNI(`foo.bar.pgedge.io`)"
```
