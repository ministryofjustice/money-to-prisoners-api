#!/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/pull_base_image.sh
docker build \
  --force-rm \
  --build-arg APP_GIT_COMMIT=${CIRCLE_SHA1} \
  --build-arg APP_GIT_BRANCH=${CIRCLE_BRANCH} \
  --build-arg APP_BUILD_TAG=${tag} \
  --build-arg APP_BUILD_DATE=$(date +%FT%T%z) \
  --tag ${tag} \
  .
mkdir -p "${CIRCLE_WORKING_DIRECTORY}/imagedump"
docker save ${tag} -o "${CIRCLE_WORKING_DIRECTORY}/imagedump/${tag}.tar.gz"
