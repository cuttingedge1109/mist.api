REGISTRY_URL?=docker.io
COMMIT_HASH?=$(shell git rev-parse HEAD)
IMAGE_REF?= $(REGISTRY_URL)/mistce/api:$(COMMIT_HASH)
API_VERSION?=v4-7-1

build:
  docker build -t $(IMAGE_REF) --build-arg API_VERSION_SHA=$(COMMIT_HASH) --build-arg API_VERSION_NAME=$(API_VERSION) --build-arg CI_API_V4_URL=https://gitlab.ops.mist.io/api/v4 .

push:
  docker push $(IMAGE_REF)
