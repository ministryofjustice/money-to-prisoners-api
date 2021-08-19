import collections
import contextlib
import datetime
import functools
import itertools
import os
import unittest
from unittest import mock

from django.core.management import call_command
from faker import Faker

from credit.constants import LOG_ACTIONS as CREDIT_ACTIONS
from credit.models import Credit, Log as CreditLog
from credit.notices import Canvas
from credit.notices.prisoner_credits import PrisonerCreditNoticeBundle
from credit.tests.test_base import BaseCreditViewTestCase
from disbursement.constants import LOG_ACTIONS as DISBURSEMENT_ACTIONS
from disbursement.models import Disbursement, Log as DisbursementLog
from prison.models import Prison, PrisonerCreditNoticeEmail

fake = Faker(locale='en_GB')
sample_location = {
    'description': 'LEI-A-2-002',
    'levels': [
        {'type': 'Wing', 'value': 'A'},
        {'type': 'Landing', 'value': '2'},
        {'type': 'Cell', 'value': '002'}
    ],
}

credit_cls = collections.namedtuple('Credit', ('amount', 'sender_name'))
disbursement_cls = collections.namedtuple('Disbursement', 'amount method recipient_first_name recipient_last_name')


class PrisonerCreditNoticeTestCase(unittest.TestCase):
    image_per_template = 3
    text_per_template = 6
    text_per_update = 3
    text_per_message = 2

    def assertPageUpdates(self, show_page, draw_string, updates_per_page):  # noqa: N802
        self.assertEqual(show_page.call_count, len(updates_per_page))
        self.assertEqual(draw_string.call_count, (
            self.text_per_template * len(updates_per_page) +
            self.text_per_update * functools.reduce(lambda updates, page: updates + len(page), updates_per_page, 0) +
            self.text_per_message * sum(itertools.chain.from_iterable(updates_per_page))
        ))

    @mock.patch.object(Canvas, 'drawImage')
    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_one_credit(self, canvas_save, canvas_show_page, canvas_draw_string, canvas_draw_image):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [credit_cls(1000, 'Mrs. Halls')], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1]])
        self.assertEqual(canvas_draw_image.call_count, self.image_per_template)

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_two_credits(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [credit_cls(1000, 'Mrs. Halls'),
                                                                  credit_cls(2000, 'Mrs. Halls')], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[2]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_two_disbursements(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [], [
            disbursement_cls(2000, 'cheque', 'Rose', 'Johnson'),
            disbursement_cls(3000, 'bank_transfer', 'Janet', 'Johnson')
        ])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[2]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_two_different_updates(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location,
                      [credit_cls(1000, 'Mrs. Halls')],
                      [disbursement_cls(2000, 'cheque', 'Mary', 'Johnson')])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1, 1]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_two_prisoners(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [credit_cls(1000, 'Mrs. Halls')], []),
                     ('RICKIE RIPPIN', 'A1617FY', sample_location, [credit_cls(2500, 'JOHNSON & ASSOCIATES')], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1], [1]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_many_credits(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [credit_cls(1000, 'Mrs. Halls')] * 11, [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[9], [2]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_one_prisoner_many_updates(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location,
                      [credit_cls(1000, 'Mrs. Halls')] * 11,
                      [disbursement_cls(2000, 'bank_transfer', 'Mary', 'Johnson')] * 11)]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[9], [2, 3], [8]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_long_text(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('NKFUVMY PMNDINERGGPGL-UMR-X-YFMESG', 'A1234AA', sample_location, [
            credit_cls(3035011, 'X' * 100)
        ], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1]])

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_location_malformed(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        malformed_location = {
            'description': 'LEIA2',
        }
        prisoners = [('JAMES HALLS', 'A1409AE', malformed_location, [credit_cls(1000, 'Mrs. Halls')], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1]])
        expected_string = 'Location: LEIA2'
        drawn_strings = [call[0][2] for call in canvas_draw_string.call_args_list]
        self.assertTrue(any(expected_string in drawn_string for drawn_string in drawn_strings))

    @mock.patch.object(Canvas, 'drawString')
    @mock.patch.object(Canvas, 'showPage')
    @mock.patch.object(Canvas, 'save')
    def test_location_complete(self, canvas_save, canvas_show_page, canvas_draw_string):
        canvas_save.return_value = None

        prisoners = [('JAMES HALLS', 'A1409AE', sample_location, [credit_cls(1000, 'Mrs. Halls')], [])]
        bundle = PrisonerCreditNoticeBundle('INB', prisoners, datetime.date(2017, 6, 16))
        bundle.render(None)

        self.assertPageUpdates(canvas_show_page, canvas_draw_string, [[1]])
        expected_string = 'Wing: A    Landing: 2    Cell: 002'
        drawn_strings = [call[0][2] for call in canvas_draw_string.call_args_list]
        self.assertTrue(any(expected_string in drawn_string for drawn_string in drawn_strings))


class NoticesCommandTestCase(BaseCreditViewTestCase):
    def assign_email_addresses(self):
        for prison in Prison.objects.all():
            PrisonerCreditNoticeEmail.objects.create(
                prison=prison,
                email='%s@mtp.local' % fake.user_name(),
            )


class CreatePrisonerNoticesTestCase(NoticesCommandTestCase):
    def setUp(self):
        super().setUp()
        self.assign_email_addresses()
        DisbursementLog.objects.filter(action=DISBURSEMENT_ACTIONS.SENT).delete()
        credited_logs = CreditLog.objects.filter(action=CREDIT_ACTIONS.CREDITED).order_by('-created')
        self.latest_log = credited_logs.first()
        credited_logs.exclude(pk=self.latest_log.pk).delete()
        self.latest_credit = self.latest_log.credit
        # leave only 1 credit as credited and no sent disbursements

    @mock.patch(
        'credit.management.commands.create_prisoner_credit_notices.can_access_nomis',
        mock.Mock(return_value=True),
    )
    @mock.patch('credit.management.commands.create_prisoner_credit_notices.PrisonerCreditNoticeBundle')
    @mock.patch('credit.management.commands.create_prisoner_credit_notices.nomis_get_location')
    def call_command(self, housing_response, expected_location, mock_get_location, bundle_class):
        credited_date = self.latest_credit.modified.date()
        location_response = {
            'nomis_id': self.latest_credit.prison.nomis_id,
            'name': self.latest_credit.prison.name,
        }
        location_response.update(housing_response)
        mock_get_location.return_value = location_response
        call_command(
            'create_prisoner_credit_notices',
            '/tmp/fake-path',
            self.latest_credit.prison.nomis_id,
            verbosity=0,
            date=credited_date.strftime('%Y-%m-%d')
        )
        bundle_class.assert_called_once_with(
            self.latest_credit.prison.name,
            [(
                self.latest_credit.prisoner_name,
                self.latest_credit.prisoner_number,
                expected_location,
                [self.latest_credit],
                [],
            )],
            self.latest_log.created.date()
        )

    def test_location_missing(self):
        self.call_command({}, None)

    def test_location_present(self):
        self.call_command(
            {
                'housing_location': {
                    'description': 'LEI-A-2-002',
                    'levels': [
                        {'type': 'Wing', 'value': 'A'},
                        {'type': 'Landing', 'value': '2'},
                        {'type': 'Cell', 'value': '002'},
                    ],
                },
            },
            {
                'description': 'LEI-A-2-002',
                'levels': [
                    {'type': 'Wing', 'value': 'A'},
                    {'type': 'Landing', 'value': '2'},
                    {'type': 'Cell', 'value': '002'},
                ],
            },
        )

    def test_location_long_form(self):
        self.call_command(
            {
                'housing_location': {
                    'description': 'HEI-1-1-A-001',
                    'levels': [
                        {'type': 'Block', 'value': '1'},
                        {'type': 'Tier', 'value': '1'},
                        {'type': 'Spur', 'value': 'A'},
                        {'type': 'Cell', 'value': '001'},
                    ],
                },
            },
            {
                'description': 'HEI-1-1-A-001',
                'levels': [
                    {'type': 'Block', 'value': '1'},
                    {'type': 'Tier', 'value': '1'},
                    {'type': 'Spur', 'value': 'A'},
                    {'type': 'Cell', 'value': '001'},
                ],
            },
        )


@mock.patch('credit.management.commands.send_prisoner_credit_notices.send_email')
@mock.patch('credit.management.commands.create_prisoner_credit_notices.nomis_get_location')
class SendPrisonerCreditNoticeTestCase(NoticesCommandTestCase):
    def test_no_emails_sent_if_prisons_have_addresses(self, nomis_get_location, mock_send_email):
        nomis_get_location.side_effect = NotImplementedError
        with open(os.devnull, 'w') as devnull, contextlib.redirect_stderr(devnull):
            call_command('send_prisoner_credit_notices', verbosity=0)
        mock_send_email.assert_not_called()

    def test_nothing_credited_sends_no_email(self, nomis_get_location, mock_send_email):
        nomis_get_location.side_effect = NotImplementedError
        self.assign_email_addresses()
        Credit.objects.credited().delete()
        Disbursement.objects.sent().delete()
        call_command('send_prisoner_credit_notices', verbosity=0)
        mock_send_email.assert_not_called()

    def test_one_email_per_prison(self, nomis_get_location, mock_send_email):
        nomis_get_location.return_value = None
        self.assign_email_addresses()
        Disbursement.objects.sent().delete()
        credited_logs = CreditLog.objects.filter(action=CREDIT_ACTIONS.CREDITED).order_by('-created')
        latest = credited_logs.first().created.date()
        credited_logs = CreditLog.objects.filter(
            action=CREDIT_ACTIONS.CREDITED,
            created__date__range=(latest, latest + datetime.timedelta(days=1))
        )
        prison_set = {credited_log.credit.prison_id for credited_log in credited_logs}
        call_command('send_prisoner_credit_notices', date=latest.strftime('%Y-%m-%d'), verbosity=0)
        self.assertEqual(len(mock_send_email.call_args_list), len(prison_set))
