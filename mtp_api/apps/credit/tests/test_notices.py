import collections
import datetime
import unittest
from unittest import mock

from django.core import mail
from django.core.management import call_command
from faker import Faker

from credit.constants import LOG_ACTIONS
from credit.models import Credit, Log
from credit.notices import Canvas
from credit.notices.prisoner_credits import PrisonerCreditNoticeBundle
from credit.tests.test_base import BaseCreditViewTestCase
from prison.models import Prison, PrisonerCreditNoticeEmail

fake = Faker(locale='en_GB')


class PrisonerCreditNoticeTestCase(unittest.TestCase):
    credit_cls = collections.namedtuple('Credit', ('amount', 'sender_name'))
    image_per_template = 3
    text_per_template = 7
    text_per_credit = 2

    def assertPageCredits(self, show_page, draw_string, credits_per_page):  # noqa
        self.assertEqual(show_page.call_count, len(credits_per_page))
        self.assertEqual(
            draw_string.call_count,
            self.text_per_template * len(credits_per_page) + self.text_per_credit * sum(credits_per_page)
        )

    @mock.patch.object(Canvas, 'drawImage')
    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_one_credit(self, canvas_save, canvas_show_page, canvas_draw_string, canvas_draw_image):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', [self.credit_cls(1000, 'Mrs. Halls')])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageCredits(canvas_show_page, canvas_draw_string, [1])
        self.assertEqual(canvas_draw_image.call_count, self.image_per_template)

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_two_credits(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', [self.credit_cls(1000, 'Mrs. Halls'),
                                                 self.credit_cls(2000, 'Mrs. Halls')])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageCredits(canvas_show_page, canvas_draw_string, [2])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_two_prisoners(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', [self.credit_cls(1000, 'Mrs. Halls')]),
                     ('RICKIE RIPPIN', 'A1617FY', [self.credit_cls(2500, 'JOHNSON & ASSOCIATES')])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageCredits(canvas_show_page, canvas_draw_string, [1, 1])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_many_credits(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', [self.credit_cls(1000, 'Mrs. Halls')] * 11)]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageCredits(canvas_show_page, canvas_draw_string, [10, 1])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_long_text(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('NKFUVMY PMNDINERGGPGL-UMR-X-YFMESG', 'A1234AA', [
            self.credit_cls(3035011, 'XFYISGB JD XQMBXB CZWNEIPTUGDS 4SJL0 PEX 2NOZ')
        ])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertEqual(canvas_show_page.call_count, 1)
        # sender name wraps to two lines (but still doesn't actually fit)
        self.assertEqual(canvas_draw_string.call_count, self.text_per_template + self.text_per_credit + 1)


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
