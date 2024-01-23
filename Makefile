
GIT_REVISION=$(shell git rev-parse --short HEAD)

IMAGE_NAME=pgedge/pgedge

DOCKER_BUILDX=docker buildx build --platform linux/amd64,linux/arm64

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) -t $(IMAGE_NAME):$(GIT_REVISION) .

.PHONY: buildx
buildx:
	$(DOCKER_BUILDX) -t $(IMAGE_NAME) -t $(IMAGE_NAME):$(GIT_REVISION) --push .

.PHONY: push
push:
	docker push $(IMAGE_NAME):$(GIT_REVISION)
	docker push $(IMAGE_NAME):latest
