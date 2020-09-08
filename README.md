# API and Django admin

Backend and internal admin site for [Prisoner Money suite of apps](https://github.com/ministryofjustice/money-to-prisoners).

## Requirements

- Unix-like platform with Python 3.6+ and NodeJS 10 (e.g. via [nvm](https://github.com/nvm-sh/nvm#nvmrc))
- PostgreSQL

## Developing

[![CircleCI](https://circleci.com/gh/ministryofjustice/money-to-prisoners-api.svg?style=svg)](https://circleci.com/gh/ministryofjustice/money-to-prisoners-api)

It's recommended that you use a python virtual environment to isolate each application.

The simplest way to do this is using:

```shell script
python3 -m venv venv    # creates a virtual environment for dependencies; only needed the first time
. venv/bin/activate     # activates the virtual environment; needed every time you use this app
```

Some build tasks expect the active virtual environment to be at `/venv/`, but should generally work regardless of
its location.

You can copy `mtp_api/settings/local.py.sample` to `local.py` to overlay local settings that won't be committed,
for example DB name, but it’s not required for a standard setup.

Create a PostgreSQL database called `mtp_api` (to use a different name, edit your local settings appropriately).

All build/development actions can be listed with `./run.py --verbosity 2 help`.

Use `./run.py serve` to run against the database configured in your local settings
or `./run.py start --test-mode` to run it with auto-generated data.
The latter is generally the most useful, especially when working with client apps and for running functional tests.

This will build everything and run the local server at [http://localhost:8000/](http://localhost:8000/).

A dockerised version can be run locally with `./run.py local_docker`,
but this does not run uWSGI like the deployed version does.

### Sample data generation

As well as the management command (`./manage.py load_test_data`), the entire data set can also be regenerated
from [Django admin](http://localhost:8000/admin/recreate-test-data/).
It's also reset when using `./run.py start --test-mode`.

These scenarios create a different set of test users for the client applications – see the user list in Django admin.

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Pull updates from Transifex with `./run.py translations --pull`.
You'll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with `./run.py translations --push`.
NB: you should pull updates before pushing to merge correctly.

## Deploying

This is handled by [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/).

## API Documentation

We have both swagger and redoc.io integration with this API.
They can be found on your development environment:
* Swagger http://localhost:8000/swagger/
* Redoc https://localhost:8000/redoc/

Similar pages are also available on the test environment

