#!/bin/bash
set -e

if [[ "${DOCKER_STATE}" == 'migrate' ]]
then
    echo "running migrate"
    python ./manage.py migrate --settings=mtp_api.settings.prod
fi

/usr/local/bin/uwsgi --ini /etc/uwsgi/magiclantern.ini
