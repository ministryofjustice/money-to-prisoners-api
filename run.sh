#!/usr/bin/env bash

cd `dirname $0`

print_usage() {
  echo "Usage: $0 [serve|testserve|test|update] [args]"
  echo "- serve [port]: run the api server on ${DEFAULT_PORT} or [port]"
  echo "- testserve [port]: run the api server in test mode on ${DEFAULT_PORT} or [port]"
  echo "- test [tests]: run the tests"
  echo "- update: update the virtual environment"
  exit 1
}

load_defaults() {
  # all constants and default values should be defined here
  DEFAULT_PORT=8000
  DEFAULT_DJANGO_SETTINGS_MODULE=mtp_api.settings
}

make_venv() {
  [ -f venv/bin/activate ] || {
    virtualenv venv
  }
}

activate_venv() {
  . venv/bin/activate
}

update_venv() {
  make_venv
  activate_venv
  pip install -U setuptools pip wheel ipython ipdb
  pip install -r requirements/dev.txt
}

choose_django_settings() {
  [ -z ${DJANGO_SETTINGS_MODULE} ] && {
    DJANGO_SETTINGS_MODULE=${DEFAULT_DJANGO_SETTINGS_MODULE}
  }
}

choose_port() {
  PORT=$1
  [ -z ${PORT} ] && {
    PORT=${DEFAULT_PORT}
  }
}

start_server() {
  choose_port $1
  # run server in foreground
  python -W default manage.py runserver 0:${PORT}
}

start_test_server() {
  choose_port $1
  load_test_data
  # run test server in foreground
  python -W default manage.py testserver --noinput --addrport 0:${PORT} test_prisons initial_groups
}

load_test_data() {
  # load test data in the background after a delay allowing test server to create the db
  PYTHONPATH=`pwd` DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE} ./devtools/load_test_data.py &
}

run_tests() {
  # run python tests
  ./manage.py test $@
}

main() {
  load_defaults

  ACTION=$1
  shift

  case ${ACTION} in
    serve)
    activate_venv
    choose_django_settings
    start_server $@
    ;;

    testserve)
    activate_venv
    choose_django_settings
    start_test_server $@
    ;;

    test)
    activate_venv
    choose_django_settings
    run_tests $@
    ;;

    update)
    update_venv
    ;;

    *)
    print_usage
    ;;
  esac
}

main $@
