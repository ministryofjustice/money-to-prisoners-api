import datetime

from django.core import mail
from django.core.management import call_command
from faker import Faker

from credit.constants import LOG_ACTIONS
from credit.models import Credit, Log
from credit.tests.test_base import BaseCreditViewTestCase
from prison.models import Prison, PrisonerCreditNoticeEmail

fake = Faker(locale='en_GB')


class SendPrisonerCreditNoticeTestCase(BaseCreditViewTestCase):
    def assign_email_addresses(self):
        for prison in Prison.objects.all():
            PrisonerCreditNoticeEmail.objects.create(
                prison=prison,
                email='%s@mtp.local' % fake.user_name(),
            )

    def test_no_emails_sent_if_prisons_have_addresses(self):
        call_command('send_prisoner_credit_notices', verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_nothing_credited_sends_no_email(self):
        self.assign_email_addresses()
        Credit.objects.credited().delete()
        call_command('send_prisoner_credit_notices', verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_one_email_per_prison(self):
        self.assign_email_addresses()
        credited_logs = Log.objects.filter(action=LOG_ACTIONS.CREDITED).order_by('-created')
        latest = credited_logs.first().created.date()
        credited_logs = Log.objects.filter(
            action=LOG_ACTIONS.CREDITED,
            created__date__range=(latest, latest + datetime.timedelta(days=1))
        )
        prison_set = {credited_log.credit.prison_id for credited_log in credited_logs}
        call_command('send_prisoner_credit_notices', date=latest.strftime('%Y-%m-%d'), verbosity=0)
        self.assertEqual(len(mail.outbox), len(prison_set))
