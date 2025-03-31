
GIT_REVISION=$(shell git rev-parse --short HEAD)

PGVS=15 16 17
SPOCK_VERSION=4.0.10
BUILD_REVISION=1

IMAGE_NAME=pgedge/pgedge

BUILDER_NAME=pgedge-builder

DOCKER_BUILDX=docker buildx build --builder $(BUILDER_NAME) --platform linux/amd64,linux/arm64

.PHONY: build
build:
	docker build -t $(IMAGE_NAME):$(GIT_REVISION) .

.PHONY: buildx-init
buildx-init:
	docker buildx create \
		--use \
		--name $(BUILDER_NAME) \
		--platform linux/arm64,linux/amd64 \
		--config ./buildkitd.toml
	docker buildx inspect --bootstrap

.PHONY: buildx
buildx: $(foreach n,$(PGVS),buildx-pg$(n))

define BUILDX_PGV
.PHONY: buildx-pg$(1)
buildx-pg$(1):
	$(DOCKER_BUILDX) --build-arg PGV=$(1) -t $(IMAGE_NAME):pg$(1)_$(SPOCK_VERSION)-$(BUILD_REVISION) --no-cache .
endef

$(foreach n,$(PGVS),$(eval $(call BUILDX_PGV,$n)))
