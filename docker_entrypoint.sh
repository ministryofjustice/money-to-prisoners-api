#!/bin/bash
set -e

if [[ "${DOCKER_STATE}" == 'reset_db' ]]
then
    echo "running migrate"
    python manage.py migrate --settings=mtp_api.settings.prod --noinput
    echo "flushing db"
    python manage.py flush --noinput --settings=mtp_api.settings.prod --noinput
    echo "running migrate (replacing fixtures)"
    python manage.py migrate --settings=mtp_api.settings.prod --noinput
    echo "loading test data"
    python manage.py load_test_data --settings=mtp_api.settings.prod
elif [[ "${DOCKER_STATE}" == 'migrate' ]]
then
    echo "running migrate"
    python ./manage.py migrate --settings=mtp_api.settings.prod --noinput
fi

/usr/local/bin/uwsgi --ini /etc/uwsgi/magiclantern.ini
