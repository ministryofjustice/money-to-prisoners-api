import datetime

from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date
from mtp_common import nomis

from credit.signals import credit_prisons_need_updating
from prison.models import Prison, PrisonerLocation
from security.signals import prisoner_profile_current_prisons_need_updating


class Command(BaseCommand):
    """
    Updates prisoner locations using Prison API
    NB: This is *not* a replacement for the prisoner location report normally submitted via noms-ops app.
    This:
    - looks up 1 prison at a time; optionally, one prisoner at a time
    - creates or updates existing prisoner location based on prisoner number based on up-to-date information
    - never deletes prisoner locations
    - cannot know if someone has been released as it does not consider the complete set of all prisoners
    """
    help = __doc__.strip().splitlines()[0]

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument('prison',
                            help='NOMIS id of prison')
        parser.add_argument('--prisoner-number',
                            help='Only update one person’s location')
        parser.add_argument('--skip-link-updates', action='store_true',
                            help='Do not update links to credits and security profiles')

    def handle(self, prison, prisoner_number=None, skip_link_updates=False, **options):
        try:
            prison = Prison.objects.get(nomis_id=prison)
        except Prison.DoesNotExist:
            raise CommandError('Unknown prison')

        # TODO: will need updating for report-upload-in-progress flag once that exists
        #       if a lock/flag is set, then error out
        if PrisonerLocation.objects.filter(active=False).exists():
            raise CommandError('Inactive locations exist. Is a report being uploaded?')

        prison_api = nomis.connector

        if prisoner_number:
            # NB: assumed to be at prison!
            prisoner_numbers = [prisoner_number]
        else:
            # currently enrolled prisoner numbers at selected prison
            prisoner_numbers = prison_api.get(f'/prison/{prison.nomis_id}/live_roll')['noms_ids']

        # load names and dates of birth
        for prisoner_number in prisoner_numbers:
            # TODO: add retry and back-off mechanism
            response = prison_api.get(f'/offenders/{prisoner_number}')

            prisoner_name = f"{response['given_name']} {response['surname']}"
            prisoner_dob = parse_date(response['prisoner_dob'])
            self.save_location(prison, prisoner_number, prisoner_name, prisoner_dob)

        if not skip_link_updates:
            credit_prisons_need_updating.send(sender=PrisonerLocation)
            prisoner_profile_current_prisons_need_updating.send(sender=PrisonerLocation)

    @transaction.atomic
    def save_location(self, prison: Prison, prisoner_number: str, prisoner_name: str, prisoner_dob: datetime.date):
        # delete inactive
        PrisonerLocation.objects.filter(
            prisoner_number=prisoner_number,
            active=False,
        ).delete()

        # create/update active
        prisoner_location, created = PrisonerLocation.objects.update_or_create(
            defaults=dict(
                prison=prison,
                prisoner_name=prisoner_name,
                prisoner_dob=prisoner_dob,
                active=True,
            ),
            prisoner_number=prisoner_number
        )
        if created:
            self.stdout.write(f'Created {prisoner_number} location')
        else:
            self.stdout.write(f'Updated {prisoner_number} location')
