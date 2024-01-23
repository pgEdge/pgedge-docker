# pgEdge Docker

This repository contains the Dockerfile used to build
[pgedge/pgedge](https://hub.docker.com/repository/docker/pgedge/pgedge)
on Docker Hub.

## Examples

### Single Node

To run a single node you can use this command:

```
docker run -it --rm -p 5432:5432 \
  -v "./examples/singlenode/db.json:/home/pgedge/db.json" \
  pgedge/pgedge
```

You can then log in using `psql` with the following command:

```
PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX \
psql -h localhost -p 5432 -U admin defaultdb
```

And of course you should customize the user passwords before using this in
any real deployment.

### Multi-Node

See [examples/swarm](examples/swarm) for a Docker Swarm example of a two node
cluster. This example can be run on both MacOS and Linux.

## Database Configuration

A simple JSON file is used to configure the database nodes. You can customize
this according to your needs, including adding more nodes and users. Always
remember to change the passwords!

```json
{
  "name": "defaultdb",
  "port": 5432,
  "nodes": [
    {
      "name": "n1",
      "region": "us-east-1",
      "hostname": "postgres-n1"
    },
    {
      "name": "n2",
      "region": "us-east-2",
      "hostname": "postgres-n2"
    }
  ],
  "users": [
    {
      "username": "admin",
      "password": "uFR44yr69C4mZa72g3JQ37GX",
      "superuser": true,
      "service": "postgres",
      "type": "admin"
    },
    {
      "username": "pgedge",
      "password": "z1Zsku10a91RS526jnVrLC39",
      "superuser": true,
      "service": "postgres",
      "type": "internal_admin"
    },
    {
      "username": "pgcat_auth",
      "password": "5Y306TW24540dEnyxp3mQBwH",
      "service": "postgres",
      "type": "pooler_auth"
    },
    {
      "username": "pgcat_admin",
      "password": "k6uu4od8r0P6lA11Oep648KC",
      "service": "pgcat",
      "type": "other"
    }
  ]
}
```
