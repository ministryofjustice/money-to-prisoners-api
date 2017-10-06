import collections
import datetime
import pathlib

from django.core.management import BaseCommand, CommandError
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware, now

from credit.constants import LOG_ACTIONS
from credit.models import Log
from credit.notices.prisoner_credits import PrisonerCreditNoticeBundle
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
            raise CommandError('Prison %s does not exist' % prison)
        if date:
            date = parse_date(date)
            if not date:
                raise CommandError('Date %s cannot be parsed, use YYYY-MM-DD format' % date)
        else:
            date = now().date() - datetime.timedelta(days=1)
        date_range = (make_aware(datetime.datetime.combine(date, datetime.time.min)),
                      make_aware(datetime.datetime.combine(date, datetime.time.max)))

        credit_logs = Log.objects.filter(
            action=LOG_ACTIONS.CREDITED,
            created__range=date_range,
            credit__prison=prison.pk,
        )
        credit_count = credit_logs.count()
        if not credit_count:
            if verbosity:
                self.stdout.write('Nothing credited at %s on %s' % (prison, date))
            return
        if verbosity > 1:
            self.stdout.write('%d credits received at %s on %s' % (credit_count, prison, date))

        prisoner_credits = collections.defaultdict(list)
        for credit in credit_logs:
            credit = credit.credit
            prisoner_credits[credit.prisoner_number].append(credit)

        prisoners = []
        for prisoner_number in sorted(prisoner_credits.keys()):
            credits = prisoner_credits[prisoner_number]
            prisoners.append((
                credits[0].prisoner_name,
                prisoner_number,
                sorted(credits, key=lambda credit: credit.received_at),
            ))

        if verbosity:
            self.stdout.write('Generating notices bundle for %s at %s' % (prison.name, path))
        bundle = PrisonerCreditNoticeBundle(prison.name, prisoners, date)
        bundle.render(str(path))
