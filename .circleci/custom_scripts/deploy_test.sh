#!/usr/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
if [[ "${CIRCLE_BRANCH}" == "master" ]]; then
  echo "Deploying to test"

  echo -n ${K8S_CLUSTER_CERT} | base64 -d > /tmp/mtp-k8s-ca.crt
  kubectl config set-cluster ${K8S_CLUSTER_NAME} --certificate-authority=/tmp/mtp-k8s-ca.crt --server=https://api.${K8S_CLUSTER_NAME}
  kubectl config set-credentials circleci --token=${K8S_TOKEN}
  kubectl config set-context ${K8S_CLUSTER_NAME} --cluster=${K8S_CLUSTER_NAME} --user=circleci --namespace=${K8S_NAMESPACE}
  kubectl config use-context ${K8S_CLUSTER_NAME}
  IMAGE=${registry}:${tag}
  kubectl patch configmap app-versions --patch "{\"data\": {\"${app}\": \"${version}\"}}"
  kubectl patch deployment ${app} --type strategic --patch "{\"metadata\": {\"annotations\": {\"kubernetes.io/change-cause\": \"${version}\"}}, \"spec\": {\"template\": {\"spec\": {\"containers\": [{\"name\": \"app\", \"image\": \"${IMAGE}\"}], \"initContainers\": [{\"name\": \"init\", \"image\": \"${IMAGE}\"},{\"name\": \"copy-static\", \"image\": \"${IMAGE}\"}]}}}}"
else
  echo "Not deploying to test"
fi

