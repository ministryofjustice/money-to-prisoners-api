#!/usr/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
echo "Cleaning ECR"

delete_images() {
  if [[ "${IMAGES_TO_DELETE}" ]]; then
    AWS_ECR_ARGS=
    for IMAGE_TO_DELETE in ${IMAGES_TO_DELETE}; do
      AWS_ECR_ARGS="${AWS_ECR_ARGS} imageDigest=${IMAGE_TO_DELETE}"
    done
    aws ecr batch-delete-image --repository-name prisoner-money/money-to-prisoners --image-ids ${AWS_ECR_ARGS}
  fi
}

echo "Deleting untagged images"
IMAGES_TO_DELETE=$(aws ecr list-images --repository-name prisoner-money/money-to-prisoners --filter tagStatus=UNTAGGED --query 'imageIds[*].imageDigest' --output text)
delete_images

if [[ "${CIRCLE_BRANCH}" != "master" ]]; then
  echo "Deleting other images from branch ${CIRCLE_BRANCH}"
  IMAGES_TO_DELETE=$(aws ecr describe-images --repository-name prisoner-money/money-to-prisoners --query 'imageDetails[?contains(map(&starts_with(@, '"'"${app}.${CIRCLE_BRANCH_LOWERCASE}."'"'), @.imageTags), `true`) && ! contains(@.imageTags, '"'"${tag}"'"')].imageDigest' --output text)
  delete_images
fi

