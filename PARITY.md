# Parity environment

This document describes the tooling built to support **parity testing** — comparing this
legacy service against its replacement, built on the organisation's standard tech stack.

Unlike the `test` environment (whose data we don't control and which we can't reset on
demand), the `parity` environment is fully controlled by this repository: its database is
wiped and reloaded from a fixed, static set of Django fixtures every day (via a cron job),
so both services are always compared against identical, reproducible data.

## How it works

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
- **`02_prisoners.json`** — 5 example prisoner locations, deliberately named/numbered so
  they're unmistakably test data at a glance: `TEST PRISONER ONE`..`FIVE`, with prisoner
  numbers `Z9901TD`..`Z9905TD` (`TD` = "Test Data"), spread across both sample prisons
  (`IXB`/`INP`), created by the fixed `admin` user (pk `1001`). No `.meta.json` either —
  prisoner locations themselves aren't date-sensitive (their linked credits/disbursements
  would be, in a future fixture).

There is deliberately **no credit/payment/disbursement data yet**. That will be added
incrementally, fixture by fixture, as the team works out what each constituent service's E2E
tests actually need (see below).

## Running it locally

The local dev stack is built and orchestrated by `money-to-prisoners-common`'s
`docker-compose.yml`, **not** the `docker-compose.yml` in this repository (this repo's own
compose file only spins up a standalone Postgres instance for running the app outside Docker
entirely — it has no `api` service). That compose file already sets `ENV: local` for the `api`
container, so no extra environment configuration is required.

1. Start the stack as normal, from `~/code/mtp/money-to-prisoners-common` (**not** from
   `money-to-prisoners-api`):
   ```shell
   docker compose up
   ```
   (or however you usually start it — this also spins up the Postgres `db` service.)
2. In another terminal, **from that same `money-to-prisoners-common` directory**, load the
   parity data set into your local database:
   ```shell
   docker compose exec api ./manage.py load_parity_data
   ```
   `docker compose` only knows about the services defined in whatever compose file(s) are in
   your *current directory* — running this from `money-to-prisoners-api` (which has its own,
   unrelated `docker-compose.yml`) will fail with `no such service: api` or
   `service "api" is not running`, even though a container with that service is genuinely
   running elsewhere.
3. That's it — your local database now contains exactly the same reference data (groups,
   prisons, users, OAuth apps/roles) as the parity environment. Log in to any of the
   constituent apps using any of the fixed accounts described above (e.g. `bank-admin` /
   `bank-admin`, or `admin` / `admin` for Django admin).

### Troubleshooting

- `service "api" is not running` / `no such service: api` / `service "mtp-api" is not running`
  — almost always means you're not in `money-to-prisoners-common` when running `docker compose`.
  `cd ~/code/mtp/money-to-prisoners-common` first. Also double check you're using the **compose
  service name** `api`, not the container name `mtp-api` shown in Docker Desktop (they're
  defined as `container_name: mtp-api` under the `api:` service key in that compose file).
- To confirm what's actually running and from where, run `docker compose ps -a` from
  `money-to-prisoners-common` — it lists every service by name alongside its container name.

Running the command without Docker (e.g. `./manage.py load_parity_data` against your own local
Postgres, per the `local.py` settings) also works out of the box, since `ENVIRONMENT` already
defaults to `'local'` when the `ENV` environment variable isn't set at all.

Re-running the command at any point completely resets your local database back to this same
known state — useful whenever your local data has drifted from what you need for a test.

## Applying it to the real parity environment

The parity environment's `ENV` variable is set to `parity` (this is a deployment/infrastructure
concern, outside this repository). The daily cron job should run:

```shell
kubectl -n money-to-prisoners-parity exec deploy/api -- ./manage.py load_parity_data
```

This mirrors the equivalent existing pattern used to refresh the `test` environment with
random data:

```shell
kubectl -n money-to-prisoners-test exec deploy/api -- ./manage.py load_test_data --number-of-prisoners 50 --credits random
```

...except `load_parity_data` takes no arguments — everything it loads is fixed by the
fixtures in the repository, not by command-line flags.

### Deploying a branch to parity before it's merged to `main`

Unlike `test` (which auto-deploys on every merge to `main`, via the `deploy` job in this
repo's `build-test-push.yml`), nothing auto-deploys to `parity` — it's not restricted to
`main` either, so you can (and should) test changes there from a feature branch/draft PR
before merging. This is done entirely from the separate `money-to-prisoners-deploy`
repository (see its `PARITY.md`/`docs/deployment.md` for the full picture); the short
version:

1. Push your branch and wait for its GitHub Actions build to go green (the same
   `build-test-push.yml` run that would eventually deploy to `test` on `main` also builds
   and pushes an image for any branch — it just doesn't auto-deploy anywhere except `main`
   → `test`). You need the whole run green, not just the initial build job, since the image
   tag is only pointed at a multi-arch manifest once `check`/`test` pass too.
2. From `money-to-prisoners-deploy`, with its virtualenv active and `git-crypt unlock` run:
   ```shell
   ./manage.py app deploy parity api <branch>.<short-commit-sha>
   ```
   e.g. `./manage.py app deploy parity api parity-env-setup.55ef31a`. This checks the image
   exists in the registry, then patches both the `app-versions` ConfigMap and the `api`
   Deployment's image for the `parity` namespace. Branch names are lower-cased in the built
   tag, so match that if your branch has capitals.
3. Confirm what's configured vs actually running:
   ```shell
   ./manage.py app versions parity
   ```
4. **Wait for the rollout to finish** before running any `manage.py` command against the
   pod — patching the Deployment only starts a rolling update, and with several replicas
   `kubectl exec deploy/api` can otherwise land on a pod that's still running the old image:
   ```shell
   kubectl -n money-to-prisoners-parity rollout status deployment/api
   ```
5. Only then run `load_parity_data` (or anything else) against the pod, as described above.

Once your branch is merged to `main`, consider re-running
`./manage.py app deploy parity api main.<sha>` (or `latest`) so `parity` doesn't stay
pinned to a stale feature-branch build indefinitely.

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

