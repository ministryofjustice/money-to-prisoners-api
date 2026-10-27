# Prisoner Money API and admin tool

Backend and internal admin site for [Prisoner Money suite of apps](https://github.com/ministryofjustice/money-to-prisoners).

How this app fits into the wider service — architecture, data flows, deployment and
support — is documented in [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/README.md).

View overview and guidelines [here](guidelines.md)

## Requirements

- Unix-like platform with Python 3.12 and NodeJS 24 (e.g. via [nvm](https://github.com/nvm-sh/nvm#installing-and-updating) or [fnm](https://github.com/Schniz/fnm#installation))
- PostgreSQL 18 (no special features are used, so the exact version is not critical)

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

### Database schema report

A [SchemaSpy](https://schemaspy.org/) report of the database structure is published every day from `main`.
It is published from `money-to-prisoners-deploy`, not from this repository, because this repository is public
and parts of the schema are sensitive. See
[Database schema report](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/schema-report.md)
for the link and who can see it.

Every table and column has a description, which the report shows and which is also stored in the database.
When you add a model or a field, give it a `db_table_comment` or `db_comment`: say what the value is, its units
and where it comes from. `core.tests.test_db_comments` fails if one is missing. This repository is public, so
descriptions of the security tables say what a column holds, never how it is used.

To generate the same report from your local database, run `./run.py schema_report`. This needs Docker.
It migrates the database configured in your local settings, then writes the report to `schema-spy-report/`
(open `schema-spy-report/index.html`). On Apple Silicon it can take 15 minutes or more, because the SchemaSpy image
only runs under emulation.

### Database migrations

Review `./manage.py sqlmigrate <app> <migration>` before releasing changes to an existing
table. Arrange those releases out of hours or behind holding pages for affected clients,
with background writers paused as needed. The deployment init container has a 5-second
lock timeout; API requests keep their normal database settings. This limits each lock wait,
not statement execution or the duration for which acquired locks are held.

Schedule concurrent index migrations (`AddIndexConcurrently`) out of hours too. The
5-second timeout also applies when `CREATE INDEX CONCURRENTLY` waits for transactions.
A failed build can leave an invalid index behind; subsequent migration attempts then fail
because the index name already exists. Follow the
[concurrent index recovery procedure](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/support.md#failed-concurrent-index-builds)
before retrying. Do not rewrite already-applied migrations such as `credit/0041`.

For **comment-only** changes, put explicit `RunSQL("COMMENT ON ...")` operations inside
`SeparateDatabaseAndState`. Keep the generated `AlterField` (or `AlterModelTableComment`)
in `state_operations`, with the full field definition matching the model, and use only
`COMMENT ON` in `database_operations`. For example, for an existing `Record.reference`
field stored in `example_record`:

```python
migrations.SeparateDatabaseAndState(
    database_operations=[
        migrations.RunSQL(
            sql='COMMENT ON COLUMN "example_record"."reference" IS \'External reference\';',
            reverse_sql='COMMENT ON COLUMN "example_record"."reference" IS \'Previous description\';',
        ),
    ],
    state_operations=[
        migrations.AlterField(
            model_name='record',
            name='reference',
            field=models.CharField(max_length=200, db_comment='External reference'),
        ),
    ],
)
```

Replace the example names, complete field definition and previous comment with the real
values; use `IS NULL` in the reverse SQL if there was no previous comment. Use the same
pattern with `COMMENT ON TABLE` and `AlterModelTableComment` for table descriptions.
Check both forward and reverse SQL and run `makemigrations --check --dry-run` to verify
that migration state still matches the models. Do not rewrite migrations already applied.

Django 5.2 can emit a no-change `ALTER COLUMN ... TYPE` for a field comment change. Besides
requiring a stronger table lock, PostgreSQL removes column statistics when changing type.
For future changes to existing columns, prefer a **separate follow-on migration** that
runs `ANALYZE` on every affected table automatically in all environments. Make it depend
on the schema migration and set `atomic = False`, so it does not extend the schema
migration's exclusive lock. For example (replace the dependency and table name):

```python
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [('your_app', 'previous_schema_migration')]

    operations = [
        migrations.RunSQL(
            'ANALYZE public.affected_table;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
```

`ANALYZE` permits ordinary reads and writes, but can contend with maintenance or DDL;
the migration lock timeout still applies. If the analysis migration fails, the preceding
schema migration may already be committed. Recover and retry, or run table-specific
`ANALYZE` manually immediately after release and verify completion. Keep that manual
fallback for releases without an analysis migration; include affected tables and an owner
in the release plan. Do not add a migration just for historical changes already applied.
See the [release steps](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/deploy-to-prod-runbook.md#database-migrations)
and [lock-timeout recovery](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/support.md#migration-lock-timeouts).
The [Django migration operations reference](https://docs.djangoproject.com/en/5.2/ref/migration-operations/#separatedatabaseandstate)
explains how database and model state operations are kept separate.

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
