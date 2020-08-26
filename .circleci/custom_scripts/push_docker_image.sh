#!/usr/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ECR_ENDPOINT}
docker load -i "${CIRCLE_WORKING_DIRECTORY}/imagedump/${tag}.tar.gz"
echo "Pushing ${tag} to ECR"
docker tag ${tag} ${registry}:${tag}
docker push ${registry}:${tag}
if [[ "${CIRCLE_BRANCH}" == "master" ]]; then
  echo "Pushing ${app} to ECR (acts as latest)"
  docker tag ${tag} ${registry}:${app}
  docker push ${registry}:${app}
fi
