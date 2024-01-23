
GIT_REVISION=$(shell git rev-parse --short HEAD)

IMAGE_NAME=pgedge/pgedge

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) -t $(IMAGE_NAME):$(GIT_REVISION) .

.PHONY: push
push:
	docker push $(IMAGE_NAME):$(GIT_REVISION)
	docker push $(IMAGE_NAME):latest
