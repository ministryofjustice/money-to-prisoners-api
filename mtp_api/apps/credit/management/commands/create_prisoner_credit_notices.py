import collections
import datetime
import pathlib

from django.core.management import BaseCommand, CommandError
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware, now
from mtp_common.nomis import can_access_nomis, get_location as nomis_get_location
import requests

from credit.constants import LOG_ACTIONS as CREDIT_ACTIONS
from credit.models import Log as CreditLog
from credit.notices.prisoner_credits import PrisonerCreditNoticeBundle
from disbursement.constants import LOG_ACTIONS as DISBURSEMENT_ACTIONS
from disbursement.models import Log as DisbursementLog
from prison.models import Prison


class Command(BaseCommand):
    """
    Creates a PDF bundle of notices to prisoners receiving credits
    """
    help = __doc__.strip().splitlines()[0]

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('path', help='Where to save the PDF.')
        parser.add_argument('prison', help='NOMIS id of prison.')
        parser.add_argument('--date', help='Credited date, defaults to yesterday.')

    def handle(self, path, prison, date=None, **options):
        verbosity = options.get('verbosity', 1)

        path = pathlib.Path(path).absolute()
        if path.exists():
            raise CommandError('Path exists %s' % path)
        try:
            prison = Prison.objects.get(pk=prison)
        except Prison.DoesNotExist:
            raise CommandError('Prison does not exist', {'prison_nomis_id', prison})
        if date:
            date = parse_date(date)
            if not date:
                raise CommandError('Date cannot be parsed, use YYYY-MM-DD format', {'date_string': date})
        else:
            date = now().date() - datetime.timedelta(days=1)
        date_range = (make_aware(datetime.datetime.combine(date, datetime.time.min)),
                      make_aware(datetime.datetime.combine(date, datetime.time.max)))

        credit_logs = CreditLog.objects.filter(
            action=CREDIT_ACTIONS.CREDITED,
            created__range=date_range,
            credit__prison=prison.pk,
        )
        credit_count = credit_logs.count()
        disbursement_logs = DisbursementLog.objects.filter(
            action=DISBURSEMENT_ACTIONS.SENT,
            created__range=date_range,
            disbursement__prison=prison.pk,
        )
        disbursement_count = disbursement_logs.count()
        if credit_count + disbursement_count == 0:
            if verbosity:
                self.stdout.write('Nothing credited or disbursed at %s on %s' % (prison, date))
            return
        if verbosity > 1:
            self.stdout.write('%d credits received, %d disbursements sent at %s on %s' % (
                credit_count, disbursement_count, prison, date,
            ))

        prisoner_updates = collections.defaultdict(lambda: {'credits': [], 'disbursements': []})
        for log in credit_logs:
            credit = log.credit
            prisoner_updates[credit.prisoner_number]['credits'].append(credit)
        for log in disbursement_logs:
            disbursement = log.disbursement
            prisoner_updates[disbursement.prisoner_number]['disbursements'].append(disbursement)

        prisoners = []
        for prisoner_number in sorted(prisoner_updates.keys()):
            credits_list = prisoner_updates[prisoner_number]['credits']
            credits_list = sorted(credits_list, key=lambda credit: credit.received_at)
            disbursements_list = prisoner_updates[prisoner_number]['disbursements']
            disbursements_list = sorted(disbursements_list, key=lambda disbursement: disbursement.modified)
            prisoner_name = (credits_list or disbursements_list)[0].prisoner_name
            location = self.get_housing(prisoner_number)
            prisoners.append((
                prisoner_name,
                prisoner_number,
                location,
                credits_list,
                disbursements_list,
            ))

        if verbosity:
            self.stdout.write('Generating notices bundle for %s at %s' % (prison.name, path))
        bundle = PrisonerCreditNoticeBundle(prison.name, prisoners, date)
        bundle.render(str(path))

    def get_housing(self, prisoner_number):
        if not can_access_nomis():
            return
        try:
            return nomis_get_location(prisoner_number, retries=2)['housing_location']
        except (TypeError, KeyError, ValueError, requests.RequestException):
            return
