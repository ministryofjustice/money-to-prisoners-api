#!/usr/bin/env sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
docker load -i "${CIRCLE_WORKING_DIRECTORY}/imagedump/${tag}.tar.gz"
TESTMODULES=$(circleci tests glob "mtp_api/apps/**/tests/test_*.py" | circleci tests split --split-by=timings | tr "/" "." | sed 's/.py//g')
docker run \
  --name postgres \
  --detach \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mtp_api \
  circleci/postgres:10.10-alpine
sleep 10
docker run \
  --name ${app} \
  -e DJANGO_SETTINGS_MODULE=mtp_api.settings.ci \
  -e DB_PASSWORD=postgres \
  -e DB_USERNAME=postgres \
  -e DB_HOST=postgres \
  -e TESTMODULES="$TESTMODULES" \
  --link postgres \
  ${tag} \
  /bin/bash -cx '/app/venv/bin/pip install -r requirements/ci.txt && cd /app && venv/bin/python manage.py test ${TESTMODULES[*]} --verbosity=2'
