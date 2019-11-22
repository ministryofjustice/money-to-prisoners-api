# API and Django admin

Backend and internal admin site for Prisoner Money suite of apps.

[Apps and libraries used as part of this service](https://github.com/ministryofjustice/money-to-prisoners)

## Requirements

- Unix-like platform with Python 3.6+ and NodeJS
- PostgreSQL

## Developing

[![CircleCI](https://circleci.com/gh/ministryofjustice/money-to-prisoners-api.svg?style=svg)](https://circleci.com/gh/ministryofjustice/money-to-prisoners-api)

Create a PostgreSQL database called `mtp_api`.

It's recommended that you use a python virtual environment to isolate each application.
Please call this `venv` and make sure it's in the root folder of this application so that `mtp_common.test_utils.code_style.CodeStyleTestCase` and the build tasks can find it.

Create a Django settings file for your local installation at `mtp_api/settings/local.py` and override the defaults as necessary.

All build/development actions can be listed with `./run.py help`.

Use `./run.py serve` to run against the database configured in your local settings or `./run.py start --test-mode` to run it with auto-generated data (use this mode for running functional tests in client apps).

This will build everything and run the local server at [http://localhost:8000](http://localhost:8000).

A dockerised version can be run locally with `./run.py local_docker`, but this does not run uWSGI like the deployed version does.

### Sample data generation

As well as the management command (`./manage.py load_test_data`), the entire data set can also be regenerated from [Django admin](http://localhost:8000/admin/recreate-test-data/).

These scenarios create a different set of test users for the client applications – see the user list in Django admin.

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Pull updates from Transifex with ``./run.py translations --pull``.
You'll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with ``./run.py translations --push``.
NB: you should pull updates before pushing to merge correctly.

## Deploying

This is handled by [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/).
