
# Copied from db.json: admin user password
export PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX

NODE_NAME?=n1

.PHONY: run
run:
	mkdir -p ./data/n1 ./data/n2
	docker stack deploy -c ./stack.yaml db

.PHONY: stop
stop:
	docker stack rm db

.PHONY: init
init:
	docker swarm init

.PHONY: connect
connect:
# Requires n1 and n2 entries in /etc/hosts
# 127.0.0.1 n1
# 127.0.0.1 n2
	PGSSLMODE=require psql -h $(NODE_NAME) -p 5432 -U admin defaultdb
