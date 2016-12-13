# Money to Prisoners API

The API app for the Money to Prisoners service. Currently, there are no APIs that are used by applications other than those that make up the Money to Prisoners Service.

[Apps and libraries used as part of this service](https://github.com/orgs/ministryofjustice/teams/money-to-prisoners/repositories)

## Requirements

- Unix-like platform with Python 3.4+ and NodeJS
- PostgreSQL 9.4+
- [Docker](https://www.docker.com/products/docker) is used for deployment, optional for development

## Developing locally

Create a PostgreSQL database called `mtp_api`. It's recommended that you use a python virtual environment to isolate each application. Create a Django settings file for your local installation at `mtp_api/settings/local.py` and override the defaults as necessary.

All build/development actions can be listed with `./run.py help`.

Use `./run.py start` to run against the database configured in your local settings or `./run.py start --test-mode` to run it with auto-generated data (use this mode for running functional tests in client apps).

A dockerised version can be run locally with `./run.py local_docker`, but this does not run uWSGI like the deployed version does.

### Sample data generation

As well as the management command (`./manage.py load_test_data`), the entire data set can also be regenerated from the Django admin tool (found at http://localhost:8000/admin/). Currently there are 2 scenarios:

* Random transaction – the standard scenario for integration testing and development (the `load_test_data` command does this by default)
* User testing the Cashbook – generates random uncredited transactions using offender names and locations from test NOMIS
* Training data for the Cashbook
* Delete prisoner location and credit data

These scenarios create a different set of test users for the client applications – see the user list in the Django admin tool.

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Pull updates from Transifex with ``./run.py translations --pull``. You'll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with ``./run.py translations --push``. NB: you should pull updates before pushing to merge correctly.

## Using the API
### Getting an access token

```
curl -X POST -d "grant_type=password&username=<user_name>&password=<password>&client_id=<client_id>&client_secret=<client_secret>" http://localhost:8000/oauth2/token/
```

If you have executed the `./manage.py load_test_data` command then you'll have some users and a test oauth2 application already created. In which case execute the following command:

```
curl -X POST -d "grant_type=password&username=test_prison_1&password=test_prison_1&client_id=cashbook&client_secret=cashbook" http://localhost:8000/oauth2/token/
```

Which will return something like:

```
{
    "expires_in": 36000,
    "access_token": "R6mYyIzZQ03Kj95iEoD53FbLPGkL7Y",
    "token_type": "Bearer",
    "scope": "write read",
    "refresh_token": "s57NweoHvPXahvmGklsrdDFMxxNSaf"
}
```

Use the `access_token` in the response in subsequent requests.
