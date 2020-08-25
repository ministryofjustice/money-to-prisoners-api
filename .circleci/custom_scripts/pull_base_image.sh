#!/usr/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ECR_ENDPOINT}
docker pull ${registry}:base-web
docker tag ${registry}:base-web base-web
