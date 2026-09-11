# Parity environment

This document describes the tooling built to support **parity testing** — comparing this
legacy service against its replacement, built on the organisation's standard tech stack.

Unlike the `test` environment (whose data we don't control and which we can't reset on
demand), the `parity` environment is fully controlled by this repository: its database is
wiped and reloaded from a fixed, static set of Django fixtures every day (via a cron job),
so both services are always compared against identical, reproducible data.

This guide gets you from a clean checkout to a passing local Playwright run. It assumes
you're running the whole stack via **Docker Compose from `money-to-prisoners-common`** —
that's the default, recommended way to run everything locally, and what the rest of this
document assumes throughout.

## Prerequisites

Clone these repositories as siblings of this one (i.e. all under the same parent directory,
e.g. `~/code/mtp/`):

- `money-to-prisoners-common` — orchestrates the local Docker Compose stack for every app
  (`api`, `cashbook`, `bank-admin`, `noms-ops`, `send-money`, `emails`, `start-page`) plus a
  Postgres `db` service. **This is the directory you'll run `docker compose` from — not this
  repo**, which has its own, unrelated `docker-compose.yml` (see "This repo's own
  `docker-compose.yml`" below).
- `money-to-prisoners-bank-admin` (and the other app repos, as needed) — each is bind-mounted
  into its container by `money-to-prisoners-common`'s compose file for live reload, so no
  separate build step is required beyond `docker compose up`.
- `hmpps-prisoner-monies-playwright-suite` — the E2E test suite that exercises the running
  stack.

## 1. Configure environment variables

`money-to-prisoners-common`'s `docker-compose.yml` already sets sensible defaults for local
dev (`ENV: local`, `DEBUG: True`, DB connection details, etc.) — no extra config is needed
just to bring the stack up. However, a couple of app features need real secrets to work
end-to-end, and those aren't (and shouldn't be) committed to the repo.

**Where secrets go:** create a `.env` file at the root of `money-to-prisoners-common` (it's
already covered by that repo's `.gitignore`, so it's safe to keep real values in it). Docker
Compose automatically loads this file and substitutes any `${VAR_NAME}` references used in
`docker-compose.yml`.

**Do not** put these in an app's own `settings/local.py` — `money-to-prisoners-common`'s
`docker-compose.yml` deliberately bind-mounts an empty stub
(`docker/no-local-settings.py`) over every app's `settings/local.py` at container runtime, so
that containers use `DB_HOST=db` rather than whatever a host-oriented `local.py` sets. Each
app's `.dockerignore` also separately excludes `settings/local.py` from ever being baked into
an image. Environment variables in `docker-compose.yml` (backed by the `.env` file) are the
only supported way to configure secrets for the Compose stack.

Currently required:

| Variable                  | Service      | Why it's needed                                                                                                                                                      |
|----------------------------|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ZENDESK_API_USERNAME`     | `bank-admin` | Bank Admin's "Get help" feedback form creates a real Zendesk ticket on submit. Without this (and the two below), the form fails silently and never redirects to `/feedback/success/`, which breaks the Playwright bank-admin get-help spec. |
| `ZENDESK_API_TOKEN`        | `bank-admin` | As above.                                                                                                                                                              |
| `ZENDESK_REQUESTER_ID`     | `bank-admin` | As above.                                                                                                                                                              |

`money-to-prisoners-common/docker-compose.yml`'s `bank-admin` service already references these
as `${ZENDESK_API_USERNAME:-}` etc. in its `environment:` block, so you only need to supply the
values. Create `money-to-prisoners-common/.env`:

```dotenv
ZENDESK_API_USERNAME=servicedesk@digital.justice.gov.uk
ZENDESK_API_TOKEN=<your-zendesk-api-token>
ZENDESK_REQUESTER_ID=<your-zendesk-requester-id>
```

Ask a teammate or check the team's secrets store for real values if you don't have them.

If you add a fixture or feature that needs a new secret in future, follow the same pattern:
add `${VAR_NAME:-}` to the relevant service's `environment:` block in
`money-to-prisoners-common/docker-compose.yml` (safe to commit — no real value in it), and
document the real value's variable name (not its value) in the table above.

## 2. Start the local stack

From `money-to-prisoners-common`:

```shell
docker compose up
```

This builds/starts every app service (`api`, `cashbook`, `bank-admin`, `noms-ops`,
`send-money`, `emails`, `start-page`) plus the shared Postgres `db` service, all on a common
Docker network so they can reach each other by service name (e.g. `bank-admin` reaches the API
at `http://api:8000`).

Leave this running in its own terminal; run the remaining steps from a second terminal.

## 3. Load the parity data set

Still from `money-to-prisoners-common` (Compose only recognises services defined in the
compose file(s) in your *current* directory — running this from `money-to-prisoners-api`
will fail with `no such service: api`, even though a container with that name is running):

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

## 4. Run the Playwright suite

From `hmpps-prisoner-monies-playwright-suite`:

```shell
npm test
```

This runs every project defined in `playwright.config.ts` against the URLs in that repo's own
`.env` (e.g. `URL_BANK_ADMIN=http://localhost:8002`), which match the ports
`money-to-prisoners-common`'s compose file publishes. To run just one app's tests:

```shell
npm run test:bank-admin
npm run test:send-money
```

## Troubleshooting

- **`service "api" is not running"` / `no such service: api`** — you're not in
  `money-to-prisoners-common` when running `docker compose`. `cd` there first. Also check
  you're using the Compose **service name** `api`, not the container name `mtp-api` shown in
  Docker Desktop (`docker compose ps -a` lists both).
- **A table looks empty even though `load_parity_data` reported success** — you're likely
  connected to the wrong Postgres instance. This repo's *own* `docker-compose.yml` (unrelated
  to the one above) spins up a separate standalone Postgres published on host port `5432`,
  purely for running the app outside Docker entirely — `money-to-prisoners-common`'s `db`
  service does not publish `5432` to the host at all, so a host-based GUI client pointed at
  `localhost:5432` cannot be looking at the data you just loaded. Verify directly instead:
  ```shell
  docker compose exec api ./manage.py shell -c "from disbursement.models import Disbursement; print(Disbursement.objects.count())"
  ```

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
- **`02_prisoners.json`** — 5 example prisoner locations, deliberately named/numbered so
  they're unmistakably test data at a glance: `TEST PRISONER ONE`..`FIVE`, with prisoner
  numbers `Z9901TD`..`Z9905TD` (`TD` = "Test Data"), spread across both sample prisons
  (`IXB`/`INP`), created by the fixed `admin` user (pk `1001`). No `.meta.json` either —
  prisoner locations themselves aren't date-sensitive (their linked credits/disbursements
  would be, in a future fixture).
- **`03_credits.json`** / **`03_credits.meta.json`** — example credits (one per sample
  prisoner), left with `"resolution": "pending"` (i.e. not yet credited/refunded) and rebased
  to stay within the last several days of "today". **Known issue:** because these are
  `pending` rather than `credited`, they're old enough to be picked up by Bank Admin's
  "Access Pay file – refunds" feature as outstanding refund candidates. This currently
  conflicts with `hmpps-prisoner-monies-playwright-suite`'s
  `tests/bank-admin/specs/test-happy-path-downloads-page.spec.ts`, which asserts that section
  says *"There are no refunds to process through Access Pay"* — i.e. it assumes no pending
  credits exist. See "Known data/test conflicts" below before changing either side.
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

### This repo's own `docker-compose.yml`

`money-to-prisoners-api` has its own `docker-compose.yml`, unrelated to the one used to run
the full local stack (see "Prerequisites" above) — it only spins up a standalone Postgres
instance (`mtp-postgres` container, `mtp_api` database, published on host port `5432`) for
running this app outside Docker entirely (e.g. `./manage.py runserver` against it directly).
It has no `api` service, so `docker compose` commands for the full stack must always be run
from `money-to-prisoners-common`, not from here. Running `./manage.py load_parity_data`
without Docker at all (against this standalone Postgres, per your own `settings/local.py`)
also works out of the box, since `ENVIRONMENT` already defaults to `'local'` when `ENV` isn't
set.

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

## Known data/test conflicts

Because fixtures are added independently, by different people, for different services'
tests, it's possible for one fixture to have a side effect that breaks an *existing* E2E test
elsewhere, without anyone intending it. This section tracks currently-known conflicts of that
kind so they aren't rediscovered/re-debugged from scratch each time.

- **`03_credits.json`'s `pending` credits vs. Bank Admin's downloads-page test.** The credits
  in `03_credits.json` are deliberately left `"resolution": "pending"` (not `credited` or
  `refunded`), rebased to stay within the last several days. Bank Admin's "Access Pay file –
  refunds" download section treats old, still-`pending` credits as outstanding refund
  candidates and generates a downloadable file for them — but
  `hmpps-prisoner-monies-playwright-suite`'s
  `tests/bank-admin/specs/test-happy-path-downloads-page.spec.ts` asserts the opposite: that
  the section shows *"There are no refunds to process through Access Pay"*, i.e. it assumes
  there's nothing pending. Whichever fixture/test was authored first didn't know about the
  other's assumption. **Not yet resolved** — needs a decision on whether to:
  - change the `03_credits.json` credits to `"resolution": "credited"` (if they were never
    meant to represent refund candidates), or
  - update the Playwright spec to expect a refund file (if parity data is *supposed* to
    include unresolved credits), or
  - split "refund-triggering" credit data into its own separate, deliberately-added fixture,
    per rule 4 above, so it's opt-in rather than a side effect of unrelated credit data.

  If you add new prisoner/credit/transaction/disbursement fixtures in future, check whether
  any existing Playwright spec (across all four apps' test suites) makes assumptions about
  there being *no* data of that kind, the way this one does — that's the class of conflict to
  watch for.

