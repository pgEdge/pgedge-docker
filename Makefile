
GIT_REVISION=$(shell git rev-parse --short HEAD)

IMAGE_NAME=pgedge/pgedge

BUILDER_NAME=pgedge-builder

DOCKER_BUILDX=docker buildx build --builder $(BUILDER_NAME) --platform linux/amd64,linux/arm64

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) -t $(IMAGE_NAME):$(GIT_REVISION) .

.PHONY: buildx-init
buildx-init:
	docker buildx create \
		--use \
		--name $(BUILDER_NAME) \
		--platform linux/arm64,linux/amd64 \
		--config ./buildkitd.toml
	docker buildx inspect --bootstrap

.PHONY: buildx
buildx:
	$(DOCKER_BUILDX) -t $(IMAGE_NAME) -t $(IMAGE_NAME):$(GIT_REVISION) --push .

.PHONY: push
push:
	docker push $(IMAGE_NAME):$(GIT_REVISION)
	docker push $(IMAGE_NAME):latest
