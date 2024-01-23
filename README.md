# pgEdge Docker

This repository contains the Dockerfile used to build
[pgedge/pgedge](https://hub.docker.com/repository/docker/pgedge/pgedge)
on Docker Hub.

See the example commands below for running pgEdge containers in Docker. You will
need to provide a JSON configuration file that specifies the database nodes and
users.

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

A Docker Swarm example of a two node cluster is located at [examples/swarm](examples/swarm).

## Enabling Replication

When the container runs, the [Spock](https://github.com/pgedge/spock) extension
is created and replication subscriptions are _automatically created_.

At this point you'll want to run your migrations or otherwise create tables. One
way to create tables on all nodes is the `spock.replicate_ddl` function. For example,
you can connect to a node with `psql` and then run:

```sql
SELECT spock.replicate_ddl('CREATE TABLE public.users (id uuid, name text, PRIMARY KEY (id))');
```

The `users` table will now exist _on all nodes_. Now you can add the table to the
default replication set by executing this command on all nodes:

```sql
SELECT spock.repset_add_all_tables('default', ARRAY['public']);
```

Having done that, you can now insert on any node and the data will be replicated
to all the other nodes. For example:

```sql
INSERT INTO users (id) SELECT gen_random_uuid();
```

There are various ways to automate these steps and more conveniences for DDL are
coming soon. You can also use [pgEdge Cloud](https://www.pgedge.com/products/pgedge-cloud)
to automate this process.

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
