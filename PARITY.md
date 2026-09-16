# Parity environment

This document describes how the `parity` environment's fixed, reproducible fixture data set is
maintained in this repository, and how to add more of it.

For how to configure and run the *whole* local stack (Docker Compose, secrets, starting
services, running the Playwright suite, and deploying a branch to the real `parity`
environment), see
[`money-to-prisoners-common`'s `PARITY.md`](https://github.com/ministryofjustice/money-to-prisoners-common/blob/main/PARITY.md)
— that's the repository you'll actually run `docker compose` from. This document only covers
the API-specific mechanics: the `load_parity_data` command, the fixtures it loads, and how to
extend them.

Unlike the `test` environment (whose data we don't control and which we can't reset on demand),
the `parity` environment is fully controlled by this repository: its database is wiped and
reloaded from a fixed, static set of Django fixtures every day (via a cron job), so both
services are always compared against identical, reproducible data.

## Loading the parity data set

From `money-to-prisoners-common` (see that repo's `PARITY.md` for the full local stack setup):

```shell
docker compose exec api ./manage.py load_parity_data
```

This wipes your local database and reloads it from the fixed set of fixtures in
`mtp_api/apps/core/fixtures/parity/` (see "How the fixtures work" below) — the exact same data
used in the real `parity` environment. Your local stack now has the same reference data
(groups, prisons, users, OAuth apps/roles) and example prisoners/credits/payments/
disbursements/transactions as `parity`.

Log in to any app using any of the fixed accounts (every password matches its username, e.g.
`bank-admin` / `bank-admin`, or `admin` / `admin` for Django admin).

Re-run this command at any point to reset your local database back to this same known state —
useful whenever your local data has drifted from what you need for a test.

### This repo's own `docker-compose.yml`

`money-to-prisoners-api` has its own `docker-compose.yml`, unrelated to the one used to run the
full local stack (see `money-to-prisoners-common`'s `PARITY.md`) — it only spins up a standalone
Postgres instance (`mtp-postgres` container, `mtp_api` database, published on host port `5432`)
for running this app outside Docker entirely (e.g. `./manage.py runserver` against it directly).
It has no `api` service, so `docker compose` commands for the full stack must always be run from
`money-to-prisoners-common`, not from here. Running `./manage.py load_parity_data` without
Docker at all (against this standalone Postgres, per your own `settings/local.py`) also works
out of the box, since `ENVIRONMENT` already defaults to `'local'` when `ENV` isn't set.

## How the fixtures work

Everything lives under:

- `mtp_api/apps/core/management/commands/load_parity_data.py` — the command that resets and
  reloads the database.
- `mtp_api/apps/core/management/commands/delete_all_data.py` — the existing command used to
  wipe the database first (also used elsewhere in this codebase).
- `mtp_api/apps/core/fixtures/parity/` — the static parity fixtures themselves.

`load_parity_data` **never generates random data**. This is a deliberate departure from
`load_test_data` (which is used to seed the `test` environment with randomised data via
`Faker`/`random`). For parity testing we need the exact same data every time, so everything
under `fixtures/parity/` is static, hand-authored JSON.

### What `load_parity_data` actually does, in order

1. Refuses to run unless `settings.ENVIRONMENT` (i.e. the `ENV` environment variable) is one
   of the `ALLOWED_ENVIRONMENTS` declared at the top of the file — currently `parity` and
   `local`. This is an **allowlist**, not a denylist, because the command is destructive
   enough (it wipes the whole database) that it should only ever run somewhere explicitly
   known to be safe. In particular, it will always refuse to run against `test` or `prod`.
2. Calls `delete_all_data` to guarantee a clean slate.
3. Loads the reference fixtures that already exist elsewhere in this codebase, unmodified and
   without any duplication: `initial_groups.json`, `initial_types.json`, `test_prisons.json`.
   These give us the standard permission groups, prison population/category types, and the two
   sample prisons (`IXB` "Prison 1", `INP` "Prison 2") that the rest of the codebase's test
   fixtures already rely on.
4. Loads every fixture found under `mtp_api/apps/core/fixtures/parity/*.json` (excluding
   `*.meta.json` files — see below), sorted alphabetically. Fixtures are numbered
   (`01_users.json`, `02_...json`, etc.) purely so the load order is obvious to anyone browsing
   the folder — Django's `loaddata` defers foreign key constraint checks until the whole load
   commits, so the numbering isn't load-bearing for correctness, just for readability.
5. For any fixture with a sibling `<name>.meta.json` file, rebases whichever date fields it
   declares so that they land relative to *today*, rather than staying fixed at whatever date
   they were authored with (see "Adding fixtures with dates" below).

### What's currently in `fixtures/parity/`

- **`01_users.json`** — hand-authored (not a `dumpdata` export) fixture containing:
  - The `admin` superuser and 10 other fixed accounts, one per role (`bank-admin`,
    `refund-bank-admin`, `disbursement-bank-admin`, `prisoner-location-admin`,
    `security-staff`, `prison-security`, `security-fiu-0`, `send-money`, and one prison clerk
    per sample prison: `test-prison-1-clerk`, `test-prison-2-clerk`).
  - **Every password is identical to its username** (e.g. user `bank-admin` has password
    `bank-admin`). This is safe because the parity environment is not internet-facing and
    contains no real user data.
  - The 4 OAuth2 applications (`cashbook`, `noms-ops`, `bank-admin`, `send-money`) and their
    roles, mirroring what `load_test_data` creates via `make_applications()` in
    `core/tests/utils.py`.
  - Prison/application/user mappings and `hmpps-employee` flags for the relevant users.
  - This file has **no dates to rebase** — nothing in it is time-sensitive, so there's no
    `01_users.meta.json`.
- **`02_prisoners.json`** — 6 example prisoner locations, deliberately named/numbered so
  they're unmistakably test data at a glance. No `.meta.json` either — prisoner locations
  themselves aren't date-sensitive (their linked credits/disbursements would be, in a future
  fixture).
- **`03_credits.json`** / **`03_credits.meta.json`** — example credits (one per sample
  prisoner), left with `"resolution": "pending"` (i.e. not yet credited/refunded) and rebased
  to stay within the last several days of "today".
- **`04_disbursement_logs.json`** — `disbursement.log` entries for the disbursements in
  `05_disbursements.json` (e.g. `created`/`confirmed`/`sent` actions), rebased via its own
  `.meta.json` alongside them.
- **`05_disbursements.json`** — 11 example disbursements spread across both sample prisoners
  and prisons, in a mix of `confirmed`/`sent` resolutions, referencing the sample prisoners
  from `02_prisoners.json` by `prisoner_number`/`prison_id` rather than by fixture pk.
- **`06_payments.json`** — example `payment.payment` records tied to some of the credits in
  `03_credits.json`, rebased in step with them.
- **`07_transactions.json`** — example `transaction.transaction` rows (bank transfer
  credits/debits), rebased via their own `.meta.json`.

More fixtures will continue to be added incrementally as the team works out what each
constituent service's E2E tests actually need (see "Adding extra data" below).

## Deploying

### Applying it to the real parity environment

The parity environment's `ENV` variable is set to `parity` (this is a deployment/infrastructure
concern, outside this repository). The daily cron job should run:

```shell
kubectl -n money-to-prisoners-parity exec deploy/api -- venv/bin/python manage.py load_parity_data
```

This mirrors the equivalent existing pattern used to refresh the `test` environment with
random data:

```shell
kubectl -n money-to-prisoners-test exec deploy/api -- ./manage.py load_test_data --number-of-prisoners 50 --credits random
```

...except `load_parity_data` takes no arguments — everything it loads is fixed by the
fixtures in the repository, not by command-line flags.

For how to deploy a branch (including this one) to the real `parity` environment before it's
merged to `main`, see `money-to-prisoners-common`'s `PARITY.md` — that process is the same for
every service, not specific to the API.

## Adding extra data (prisoners, credits, payments, etc.)

As the team identifies what data each service's E2E tests need, add it as a new numbered
fixture under `mtp_api/apps/core/fixtures/parity/`, e.g. `02_prisoners.json`. A few rules to
follow to stay consistent with what's already there:

1. **Number it.** Pick the next free two-digit prefix (`02_`, `03_`, ...) so the load order is
   obvious at a glance. This isn't required for FK correctness (see above) but keeps the folder
   readable.
2. **Reference existing fixed data by its pk**, rather than duplicating it. For example, a new
   prisoner-location fixture should reference the sample prisons already loaded from
   `test_prisons.json` (`"prison": "IXB"` or `"prison": "INP"`), and any credits/payments
   should reference the fixed user accounts already in `01_users.json` by their pk (e.g.
   `1010` for `test-prison-1-clerk`) rather than creating new ones, unless a new named account
   is genuinely needed.
3. **If the fixture contains dates that need to stay "current" relative to today** (e.g. a
   credit that must always appear "3 days ago" so a report's rolling 7-day window keeps
   showing it), add a sibling meta file, e.g. `02_prisoners.meta.json`:
   ```json
   {
     "anchor_date": -3,
     "authored_date": "2026-01-01",
     "date_fields": {
       "credit.credit": ["received_at", "created", "modified"]
     }
   }
   ```
   - `authored_date` is the date you used when writing the dates inside `02_prisoners.json`
     (e.g. if a credit's `"created"` field is `"2026-01-01T12:00:00Z"`, put `"2026-01-01"`
     here).
   - `anchor_date` is a **signed day offset from today**: `-3` means "3 days in the past",
     `3` would mean "3 days in the future". Negative-for-the-past was chosen deliberately so
     it reads naturally, since most parity data will represent historical activity.
   - `date_fields` maps `app_label.model_name` to the list of field names on that model that
     should be shifted. **Note this shifts every row of that model across every fixture that
     touches it** — the shift is applied per-model, not per-fixture-row — so if two fixtures
     both add rows to the same model with different intended offsets, they need separate
     models, or you'll need to reconsider the split.
   - The shift applied is always `(today + anchor_date) - authored_date`, applied as a single
     bulk `UPDATE ... SET field = field + shift` after all fixtures have loaded, so relative
     spacing between records in your fixture (e.g. "3 days apart from each other") is
     preserved exactly — the whole block just slides forward (or backward) together.
4. **Keep prisoner/credit fixtures blank until they're actually needed.** Per the current plan,
   only reference/structural data (users, groups, prisons) ships by default; add prisoner and
   transactional data only once a specific E2E test requires it, to keep the data set small and
   intentional.

After adding a new fixture (and optional meta file), just re-run `load_parity_data` (locally or
in the real parity environment) — it will pick up the new file automatically via its glob, no
other changes required.
