
export PGPASSWORD=uFR44yr69C4mZa72g3JQ37GX

.PHONY: run
run:
	docker stack deploy -c ./stack.yaml db

.PHONY: stop
stop:
	docker stack rm db

.PHONY: init
init:
	docker swarm init

.PHONY: connect
connect:
	PGSSLMODE=require psql -h localhost -p 5432 -U admin defaultdb
