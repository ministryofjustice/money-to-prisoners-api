# Prisoner Money API and admin tool

Backend and internal admin site for [Prisoner Money suite of apps](https://github.com/ministryofjustice/money-to-prisoners).

How this app fits into the wider service — architecture, data flows, deployment and
support — is documented in [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/README.md).

View overview and guidelines [here](guidelines.md)

## Requirements

- Unix-like platform with Python 3.12 and NodeJS 24 (e.g. via [nvm](https://github.com/nvm-sh/nvm#installing-and-updating) or [fnm](https://github.com/Schniz/fnm#installation))
- PostgreSQL 14 (though the version is not a strict requirement as no special features are used)

## Developing

[![Build, test and push](https://github.com/ministryofjustice/money-to-prisoners-api/actions/workflows/build-test-push.yml/badge.svg)](https://github.com/ministryofjustice/money-to-prisoners-api/actions/workflows/build-test-push.yml)

It’s recommended that you use a python virtual environment to isolate each application.

The simplest way to do this is using:

```shell
python3 -m venv venv    # creates a virtual environment for dependencies; only needed the first time
. venv/bin/activate     # activates the virtual environment; needed every time you use this app
```

Some build tasks expect the active virtual environment to be at `/venv/`, but should generally work regardless of
its location.

You can copy `mtp_api/settings/local.py.sample` to `local.py` to overlay local settings that won’t be committed,
for example, DB name, but it’s not required for a standard setup.

Create a PostgreSQL database called `mtp_api` (to use a different name, edit your local settings appropriately).

All build/development actions can be listed with `./run.py --verbosity 2 help`.

Use `./run.py serve` to run against the database configured in your local settings
or `./run.py start --test-mode` to run it with auto-generated data.
The latter is generally the most useful, especially when working with client apps and for running functional tests.

This will build everything and run the local server at [http://localhost:8000/](http://localhost:8000/).

To run the API together with the client apps, see the [getting-started guide](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/getting-started.md):
each client app's repository has a `docker-compose.yml` that runs the published API image with test data.

### Sample data generation

As well as the management command (`./manage.py load_test_data`), the entire data set can also be regenerated
from [Django admin](http://localhost:8000/admin/testing/recreate-data/).
It’s also reset when using `./run.py start --test-mode`.

These scenarios create a different set of test users for the client applications – see the user list in Django admin.
The users created by `load_test_data` are listed in the [getting-started guide](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/getting-started.md#test-logins).

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Requires [transifex cli tool](https://github.com/transifex/cli#installation) for synchronisation:

Pull updates from Transifex with `./run.py translations --pull`.
You’ll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with `./run.py translations --push`.
NB: you should pull updates before pushing to merge correctly.

### Parity testing

See [PARITY.md](PARITY.md) for how this repository's fixed, reproducible fixture data set (used
to compare this service against its replacement) is structured and how to add more of it. See
[`money-to-prisoners-common`'s `PARITY.md`](https://github.com/ministryofjustice/money-to-prisoners-common/blob/main/PARITY.md)
for how to run/orchestrate the whole local parity stack and Playwright suite.

## Deploying

This is handled by [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/).

## API Documentation

We have both swagger and redoc.io integration with this API.
They can be found on your development environment:
* Swagger: http://localhost:8000/swagger/
* Redoc: http://localhost:8000/redoc/

Similar pages are also available on the test environment

## Additional Bespoke Packages

There are several dependencies of the ``money-to-prisoners-api`` python library which are maintained by this team, so they may require code-changes when the dependencies (e.g. Django) of the ``money-to-prisoners-api`` python library are incremented.

* django-moj-irat: https://github.com/ministryofjustice/django-moj-irat
