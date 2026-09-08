import glob
import json
import os
import textwrap

from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db.models import F
from django.utils import timezone

PARITY_FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'fixtures', 'parity'
)

# NB: this is an allowlist, not a denylist (unlike e.g. `delete_all_data`'s `ENVIRONMENT != 'prod'`
# check), because this command is destructive enough (wipes the whole database) that it should only
# ever run somewhere it's explicitly known to be safe:
# - 'parity': the shared parity testing environment, reset daily via cron
# - 'local': a developer's own machine, whether run bare or via money-to-prisoners-common's
#            docker-compose (which sets ENV=local for the api container), for local E2E test work
ALLOWED_ENVIRONMENTS = {'parity', 'local'}


class Command(BaseCommand):
    """
    Resets the database and reloads it from a fixed set of static fixtures, intended to allow
    reproducible parity testing between this legacy service and its replacement.

    Only runs in the parity environment or a developer's local environment (see
    ALLOWED_ENVIRONMENTS in this file) - refuses to run anywhere else, in particular the shared
    test environment, to avoid accidentally wiping data that this command doesn't control.

    Unlike `load_test_data`, this command never generates random data: everything it loads
    comes from JSON fixtures under `core/fixtures/parity/`, each named with a numeric prefix
    (e.g. `01_users.json`) purely to make load order obvious to engineers browsing the folder.

    Any fixture that contains dates that should stay "current" (e.g. credits/payments used to
    test rolling report windows) may have a sibling `<name>.meta.json` file declaring an
    `anchor_date` (a signed day offset from today, e.g. -3 for 3 days ago) and the model
    fields that should be shifted by `today + anchor_date` relative to the dates as authored
    in the fixture.

    Designed to be run daily (e.g. via a cron job) to reset the parity environment, and on-demand
    by developers to set up their local database for local E2E test creation.
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        if settings.ENVIRONMENT not in ALLOWED_ENVIRONMENTS:
            raise CommandError(
                f'This command can only be run in one of {sorted(ALLOWED_ENVIRONMENTS)} '
                f'(ENV={settings.ENVIRONMENT!r}), refusing to run here to avoid accidentally '
                f'wiping test or production data'
            )

        verbosity = options.get('verbosity', 1)
        print_message = self.stdout.write if verbosity else lambda m: m

        print_message('Deleting all data')
        call_command('delete_all_data', verbosity=verbosity)

        fixture_files = sorted(glob.glob(os.path.join(PARITY_FIXTURES_DIR, '*.json')))
        fixture_files = [f for f in fixture_files if not f.endswith('.meta.json')]
        if not fixture_files:
            raise CommandError(f'No parity fixtures found in {PARITY_FIXTURES_DIR}')

        print_message('Loading reference fixtures (groups, prison types, prisons)')
        call_command(
            'loaddata', 'initial_groups.json', 'initial_types.json', 'test_prisons.json',
            verbosity=verbosity,
        )

        print_message(f'Loading parity fixtures: {", ".join(os.path.basename(f) for f in fixture_files)}')
        call_command('loaddata', *fixture_files, verbosity=verbosity)

        for fixture_file in fixture_files:
            meta_file = fixture_file[:-len('.json')] + '.meta.json'
            if not os.path.exists(meta_file):
                continue
            print_message(f'Rebasing dates for {os.path.basename(fixture_file)}')
            self.rebase_dates(meta_file, print_message)

    def rebase_dates(self, meta_file, print_message):
        with open(meta_file) as f:
            meta = json.load(f)

        anchor_date = meta['anchor_date']
        target_date = timezone.localdate() + timezone.timedelta(days=anchor_date)
        authored_date = timezone.datetime.strptime(meta['authored_date'], '%Y-%m-%d').date()
        shift = target_date - authored_date

        for model_label, fields in meta['date_fields'].items():
            app_label, model_name = model_label.split('.')
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                raise CommandError(f'Could not find model {model_label} referenced in {meta_file}')

            update_kwargs = {field: F(field) + shift for field in fields}
            model.objects.all().update(**update_kwargs)
            print_message(f'  Shifted {", ".join(fields)} on {model_label} by {shift}')
