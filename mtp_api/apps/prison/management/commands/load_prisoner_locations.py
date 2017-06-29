import datetime
import re
from urllib.parse import urljoin

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db.transaction import atomic
from django.utils.dateparse import parse_date
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from credit.signals import credit_prisons_need_updating
from prison.models import Prison, PrisonerLocation


class Command(BaseCommand):
    """
    Load prisoner locations from Single Offender ID service
    """
    help = __doc__.strip()
    excluded_nomis_ids = {'ZCH'}  # prison NOMIS ids which MTP ignores
    released_establishment_code = 'OUT'  # offender has been released
    ignored_establishment_code = {'OUT', 'TRN'}  # not actual establishments

    def add_arguments(self, parser):
        super().add_arguments(parser)
        if settings.OFFENDER_API_URL:
            offender_endpoint = urljoin(settings.OFFENDER_API_URL, '/api/offenders')
            oauth_endpoint = urljoin(settings.OFFENDER_API_URL, '/oauth/token')
        else:
            offender_endpoint = ''
            oauth_endpoint = ''
        parser.add_argument('--offender-endpoint', default=offender_endpoint)
        parser.add_argument('--oauth-endpoint', default=oauth_endpoint)
        parser.add_argument('--oauth-client', default=settings.OFFENDER_API_CLIENT_ID)
        parser.add_argument('--oauth-secret', default=settings.OFFENDER_API_CLIENT_SECRET)
        parser.add_argument('--page-size', default=500, type=int)
        parser.add_argument('--modified-only', action='store_true')

    def handle(self, **options):
        if not all(
            options.get(field)
            for field in ('offender_endpoint', 'oauth_endpoint', 'oauth_client', 'oauth_secret')
        ):
            raise CommandError('Missing Single Offender ID details')

        verbosity = options.get('verbosity', 1)
        modified_only = options['modified_only']
        name_fields = ('given_name_1', 'given_name_2', 'given_name_3', 'surname')
        whitespace = re.compile(r'\s+')

        known_prisons = set(Prison.objects.values_list('nomis_id', flat=True)) - self.excluded_nomis_ids
        if verbosity:
            self.stdout.write('%d known prisons' % len(known_prisons))
            self.stdout.write('Starting Single Offender ID session')
        session = OAuth2Session(
            client=BackendApplicationClient(client_id=options['oauth_client'])
        )
        session.fetch_token(
            token_url=options['oauth_endpoint'],
            client_id=options['oauth_client'],
            client_secret=options['oauth_secret'],
        )

        PrisonerLocation.objects.filter(active=False).delete()
        query = {
            'per_page': options['page_size'],
        }
        if modified_only and PrisonerLocation.objects.exists():
            updated_after = PrisonerLocation.objects.latest().created - datetime.timedelta(minutes=5)
            if verbosity > 1:
                self.stdout.write('Only loading offenders modified since %s' % updated_after)
            query['updated_after'] = updated_after.strftime('%Y-%m-%dT%H:%M:%S')
        page = 1
        locations_updated = 0
        while True:
            response = session.get(
                options['offender_endpoint'],
                params=dict(page=page, **query)
            )
            prisoners = response.json()
            if not prisoners:
                break
            prisoner_locations = []
            locations_to_delete = []
            for prisoner in prisoners:
                single_offender_id = prisoner['id']
                prisoner_number = prisoner.get('noms_id')
                if not prisoner_number:
                    self.stderr.write('Offender %s has no prisoner number' % single_offender_id)
                    continue
                prison_id = prisoner.get('establishment_code')
                if modified_only and prison_id == self.released_establishment_code:
                    if verbosity > 1:
                        self.stdout.write('Will delete location for %s' % prisoner_number)
                    locations_to_delete.append(prisoner_number)
                    continue
                elif prison_id not in known_prisons:
                    if verbosity > 1 and prison_id not in self.ignored_establishment_code:
                        self.stdout.write('Unknown establishment code %s for %s' % (prison_id, prisoner_number))
                    continue
                prisoner_dob = parse_date(prisoner.get('date_of_birth') or '')
                if not prisoner_dob:
                    self.stderr.write('Offender %s (%s) has no date of birth' % (prisoner_number, single_offender_id))
                    continue
                prisoner_name = ' '.join(prisoner.get(field) or '' for field in name_fields)
                prisoner_name = whitespace.sub(' ', prisoner_name)
                prisoner_locations.append(
                    PrisonerLocation(
                        single_offender_id=single_offender_id,
                        prisoner_number=prisoner_number,
                        prison_id=prison_id,
                        prisoner_dob=prisoner_dob,
                        prisoner_name=prisoner_name,
                    )
                )
            with atomic():
                if modified_only:
                    for prisoner_location in prisoner_locations:
                        prisoner_location.active = True
                        locations_to_delete.append(prisoner_location.prisoner_number)
                    PrisonerLocation.objects.filter(prisoner_number__in=locations_to_delete).delete()
                PrisonerLocation.objects.bulk_create(prisoner_locations)
            page += 1
            locations_updated += len(prisoner_locations)

        if not modified_only:
            with atomic():
                PrisonerLocation.objects.filter(active=True).delete()
                PrisonerLocation.objects.filter(active=False).update(active=True)

        credit_prisons_need_updating.send(sender=PrisonerLocation)

        if verbosity:
            self.stdout.write('%d prisoner locations loaded' % locations_updated)
