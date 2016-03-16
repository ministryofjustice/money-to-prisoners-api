##############################
#### MAKEFILE FOR MTP API ####
##############################

# default parameters, can be overridden when calling make
app=api
port ?= 8000
django_settings ?= mtp_api.settings
python_requirements ?= requirements/dev.txt
verbosity ?= 1

ifeq ($(shell [ $(verbosity) -gt 1 ] && echo true),true)
TASK_OUTPUT_REDIRECTION := &1
PYTHON_WARNINGS := "-W default"
else ifeq ($(shell [ $(verbosity) -eq 0 ] && echo true),true)
TASK_OUTPUT_REDIRECTION := /dev/null
PYTHON_WARNINGS := "-W ignore"
else
TASK_OUTPUT_REDIRECTION := /dev/null
PYTHON_WARNINGS := "-W once"
endif

#################
#### RECIPES ####
#################

# usage instructions
.PHONY: print_usage
print_usage:
	@echo "Usage: make [serve|testserve|docker|test|update] [args]"
	@echo "- serve [port]: run the api server on http://localhost:$(port)/"
	@echo "- testserve [port]: run the api server in test mode on http://localhost:$(port)/"
	@echo "- docker: build and run using Docker locally"
	@echo "- test [tests]: run the tests"
	@echo "- update: update the virtual environment"

# migrate the db
.PHONY: migrate_db
migrate_db: venv/bin/python
	@venv/bin/python manage.py migrate --verbosity=$(verbosity) --noinput >$(TASK_OUTPUT_REDIRECTION)

# collect django static assets
.PHONY: static_assets
static_assets: venv/bin/python
	@echo Collecting static Django assets
	@venv/bin/python manage.py collectstatic --verbosity=$(verbosity) --noinput >$(TASK_OUTPUT_REDIRECTION)

# run the server normally
.PHONY: serve
serve: venv/bin/python
	@echo "Starting MTP $(app) on http://localhost:$(port)/"
	@venv/bin/python $(PYTHON_WARNINGS) manage.py runserver 0:$(port)

# run the server in testing mode (allows test data replenishment)
.PHONY: testserve
testserve: update
	@echo "Starting MTP $(app) on http://localhost:$(port)/ in test mode"
	@venv/bin/python $(PYTHON_WARNINGS) manage.py testserver --noinput --addrport 0:$(port) initial_groups test_prisons

# build and run using docker locally
.PHONY: docker
docker: .host_machine_ip
	@docker-compose build
	@echo "Starting MTP $(app) in Docker on http://$(HOST_MACHINE_IP):$(port)/ in test mode"
	@docker-compose up

# run uwsgi, this is the entry point for docker running remotely
uwsgi: venv/bin/uwsgi migrate_db static_assets
ifneq ($(ENV),prod)
	@echo "Starting API load data listener on port 8800"
	@venv/bin/python $(PYTHON_WARNINGS) manage.py load_data_listener &
endif
	@echo "Starting MTP $(app) in uWSGI"
	@venv/bin/uwsgi --ini conf/uwsgi/api.ini

# run python tests
.PHONY: test
test: venv/bin/python
	@venv/bin/python $(PYTHON_WARNINGS) manage.py test --verbosity=$(verbosity) $(tests)

# update python virtual environment
.PHONY: update
update: venv/bin/pip
	@echo Updating python packages
	@venv/bin/pip install -U setuptools pip wheel ipython ipdb >$(TASK_OUTPUT_REDIRECTION)
	@venv/bin/pip install -r $(python_requirements) >$(TASK_OUTPUT_REDIRECTION)

# update environment and collect static files
.PHONY: build
build: update static_assets

##########################
#### INTERNAL RECIPES ####
##########################

# determine host machine ip, could be running via docker machine
.PHONY: .host_machine_ip
.host_machine_ip: .docker_machine
HOST_MACHINE_IP := $(strip $(shell docker-machine ip default 2>/dev/null))
ifeq ($(HOST_MACHINE_IP),)
HOST_MACHINE_IP := localhost
endif
export HOST_MACHINE_IP

# connect to docker-machine if necessary
.PHONY: .docker_machine
.docker_machine:
ifneq ($(strip $(shell which docker-machine)),)
	@[ `docker-machine status default` = "Running" ] && echo 'Machine "default" is already running.' || docker-machine start default
	$(eval DOCKER_MACHINE_ENV := $(shell docker-machine env default))
	$(eval export DOCKER_MACHINE_NAME := $(shell echo '$(DOCKER_MACHINE_ENV)' | sed 's/.*DOCKER_MACHINE_NAME="\([^"]*\)".*/\1/'))
	$(eval export DOCKER_HOST := $(shell echo '$(DOCKER_MACHINE_ENV)' | sed 's/.*DOCKER_HOST="\([^"]*\)".*/\1/'))
	$(eval export DOCKER_CERT_PATH := $(shell echo '$(DOCKER_MACHINE_ENV)' | sed 's/.*DOCKER_CERT_PATH="\([^"]*\)".*/\1/'))
	$(eval export DOCKER_TLS_VERIFY := $(shell echo '$(DOCKER_MACHINE_ENV)' | sed 's/.*DOCKER_TLS_VERIFY="\([^"]*\)".*/\1/'))
endif

######################
#### FILE TARGETS ####
######################

venv/bin/python, venv/bin/pip:
	@echo Creating python virtual environment
	@virtualenv -p python3 venv >$(TASK_OUTPUT_REDIRECTION)

venv/bin/uwsgi: venv/bin/pip
	@venv/bin/pip install uWSGI
