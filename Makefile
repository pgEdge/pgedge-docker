
GIT_REVISION=$(shell git rev-parse --short HEAD)

PGVS=15 16 17
SPOCK_VERSION=4.0.10
BUILD_REVISION=2

IMAGE_NAME = pgedge/pgedge

OS ?= linux
ARCH ?= $(shell uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')
PLATFORM ?= $(OS)/$(ARCH)
PLATFORM_ARG ?= $(if $(PLATFORM),--platform=$(PLATFORM),)

IMAGE_TAG ?= pg$(1)_$(SPOCK_VERSION)-$(BUILD_REVISION)
IMAGE_TAG_LATEST ?= pg$(1)-latest
IMAGE_TAG_LOCAL ?= pg$(1)-$(GIT_REVISION)-$(ARCH)
BUILDER_NAME = pgedge-builder
REPO ?= https://pgedge-download.s3.amazonaws.com/REPO
DOCKER_BUILDX = docker buildx build --builder $(BUILDER_NAME) --platform linux/amd64,linux/arm64

.PHONY: build
build: $(foreach n,$(PGVS),build-pg$(n))

define BUILD_PGV
.PHONY: build-pg$(1)
build-pg$(1):
	docker build $(PLATFORM_ARG) --build-arg PGV=$(1) --build-arg REPO=$(REPO) -t $(IMAGE_NAME):$(IMAGE_TAG_LOCAL) .
endef

$(foreach n,$(PGVS),$(eval $(call BUILD_PGV,$n)))

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
	$(DOCKER_BUILDX) --build-arg PGV=$(1) --build-arg REPO=$(REPO) -t $(IMAGE_NAME):$(call IMAGE_TAG,$(1)) -t $(IMAGE_NAME):$(call IMAGE_TAG_LATEST,$(1)) --no-cache .
endef

$(foreach n,$(PGVS),$(eval $(call BUILDX_PGV,$n)))

.PHONY: test
test: $(foreach n,$(PGVS),test-pg$(n))

define TEST_PGV
.PHONY: test-pg$(1)
test-pg$(1):
	go run tests/main.go $(IMAGE_NAME):$(IMAGE_TAG_LOCAL) $(PWD)/tests/db.json
endef

$(foreach n,$(PGVS),$(eval $(call TEST_PGV,$n)))