#!/bin/env sh

export CIRCLE_BRANCH_LOWERCASE=$(echo $CIRCLE_BRANCH | tr '[:upper:]' '[:lower:]')

export registry=${ECR_ENDPOINT}/prisoner-money/money-to-prisoners
export version=${CIRCLE_BRANCH_LOWERCASE}.${CIRCLE_SHA1:0:7}
export tag=${app}.${version}
