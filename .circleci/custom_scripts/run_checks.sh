#!/usr/bin/env sh

. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/common.sh
. ${CIRCLE_WORKING_DIRECTORY}/.circleci/custom_scripts/start_db_container.sh

docker load -i "${CIRCLE_WORKING_DIRECTORY}/imagedump/${tag}.tar.gz"

docker run \
  --name ${app} \
  -e DJANGO_SETTINGS_MODULE=mtp_api.settings.ci \
  -e DB_PASSWORD=postgres \
  -e DB_USERNAME=postgres \
  -e DB_HOST=postgres \
  --link postgres \
  ${tag} \
  /bin/bash -cx 'cd /app/ && venv/bin/python manage.py check --verbosity=2 && venv/bin/python manage.py makemigrations --check --verbosity=2'
