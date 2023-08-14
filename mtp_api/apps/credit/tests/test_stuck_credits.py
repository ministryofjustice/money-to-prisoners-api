import datetime
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker
from parameterized import parameterized
import responses

from core.tests.utils import make_test_users
from credit.management.commands.fix_stuck_credits import find_credits_in_nomis, nomis_transaction_already_linked
from credit.constants import CreditResolution, CreditStatus
from credit.models import Credit
from payment.constants import PaymentStatus
from payment.models import Payment


# silence check for interactive console:
@mock.patch('credit.management.commands.fix_stuck_credits.sys.stdin.isatty', new=lambda: True)
@override_settings(
    HMPPS_CLIENT_SECRET='test-secret',
    HMPPS_AUTH_BASE_URL='https://sign-in-dev.hmpps.local/auth/',
    HMPPS_PRISON_API_BASE_URL='https://api-dev.prison.local/',
)
class FixStuckCreditsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    # test command inputs
    sample_prison = 'IXB'
    sample_date = '2021-10-10'
    sample_username = 'test-prison-1'

    # returned test data
    sample_prisoner_number = 'A1409AE'
    nomis_transaction_matching = {
        'id': '1234501-1',
        'type': {'code': 'MTDS', 'desc': 'Money through digital service'},
        'description': 'Sent by Mrs. Halls',  # matches uncredited credit
        'amount': 3000,  # matches uncredited credit
        'date': '2021-10-11',
    }
    nomis_transaction_different_1 = {
        'id': '1234502-1',
        'type': {'code': 'MTDS', 'desc': 'Money through digital service'},
        'description': 'Sent by Mr. Johnson',  # name will not match
        'amount': 3000,
        'date': '2021-10-11',
    }
    nomis_transaction_different_2 = {
        'id': '1234503-1',
        'type': {'code': 'MTDS', 'desc': 'Money through digital service'},
        'description': 'Sent by Mrs. Halls',
        'amount': 1000,  # amount will not match
        'date': '2021-10-11',
    }

    def setUp(self):
        super().setUp()
        make_test_users(clerks_per_prison=1, num_security_fiu_users=0)
        self.credit = None

        # clear all caches
        cache.clear()  # holds HMPPS Auth token
        find_credits_in_nomis.cache_clear()
        nomis_transaction_already_linked.cache_clear()

    def mock_uncredited_credits(self):
        credit: Credit = baker.make(
            Credit,
            prisoner_number=self.sample_prisoner_number,
            prisoner_name='JAMES HALLS',
            prison_id=self.sample_prison,
            amount=3000,
            received_at=timezone.make_aware(datetime.datetime(2021, 10, 10, 9)),
            resolution=CreditResolution.pending.value,
        )
        baker.make(
            Payment,
            credit=credit,
            amount=credit.amount,
            status=PaymentStatus.taken,
            cardholder_name='Mrs. Halls',
        )
        self.credit = credit

    @classmethod
    def mock_nomis_response(cls, rsps: responses.RequestsMock, matching_count=1):
        # mock getting access token from HMPPS Auth
        rsps.add(
            responses.POST,
            f'{settings.HMPPS_AUTH_BASE_URL}oauth/token',
            json={
                'access_token': 'fake-token',
                'expires_in': 3600,
            },
        )
        # mock getting transactions from Prison API
        transactions = [
            cls.nomis_transaction_matching
            for _ in range(matching_count)
        ]
        transactions += [
            cls.nomis_transaction_different_1,
            cls.nomis_transaction_different_2,
        ]
        rsps.add(
            responses.GET,
            f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/'
            f'prison/{cls.sample_prison}/offenders/{cls.sample_prisoner_number}/accounts/cash/transactions',
            json={'transactions': transactions},
            # asserts that transaction date search range is correct:
            match=[responses.matchers.query_param_matcher({'from_date': '2021-10-11', 'to_date': '2021-10-15'})],
        )

    @parameterized.expand([
        ('Prison 1', sample_date, sample_username, 'Unknown prison'),
        (sample_prison, '10 Oct 2021', sample_username, 'Date cannot be parsed'),
        (sample_prison, sample_date, 'Prison Clerk', 'Username not found'),
    ])
    @mock.patch('credit.management.commands.fix_stuck_credits.find_uncredited_credits')
    def test_arguments(self, prison, date, owner, error_msg, mocked_uncredited_credits):
        mocked_uncredited_credits.return_value = []

        with self.assertRaises(CommandError) as e, responses.RequestsMock():
            call_command('fix_stuck_credits', prison, date, owner)

        self.assertIn(error_msg, str(e.exception))

    def assertCreditLinked(self):  # noqa: N802
        credit: Credit = self.credit
        credit.refresh_from_db()

        # assert that credit is now linked to matching NOMIS transaction
        self.assertEqual(credit.resolution, CreditResolution.credited.value)
        self.assertEqual(credit.status, CreditStatus.credited.value)
        self.assertEqual(credit.nomis_transaction_id, self.nomis_transaction_matching['id'])
        self.assertEqual(credit.owner.username, self.sample_username)

    def assertCreditNotLinked(self, mocked_mark_credited):  # noqa: N802
        credit: Credit = self.credit
        credit.refresh_from_db()

        # assert that credit is NOT linked to any NOMIS transactions
        self.assertEqual(credit.resolution, CreditResolution.pending.value)
        self.assertEqual(credit.status, CreditStatus.credit_pending.value)
        self.assertIsNone(credit.nomis_transaction_id)
        self.assertIsNone(credit.owner)

        mocked_mark_credited.assert_not_called()

    @mock.patch('credit.management.commands.fix_stuck_credits.input', new=lambda _: 'y')  # auto-answer yes
    def test_one_matching_credit(self):
        self.mock_uncredited_credits()
        with responses.RequestsMock() as rsps:
            self.mock_nomis_response(rsps)
            call_command('fix_stuck_credits', self.sample_prison, self.sample_date, self.sample_username)

        self.assertCreditLinked()

    @mock.patch('credit.management.commands.fix_stuck_credits.input', new=lambda _: 'y')  # not prompted
    @mock.patch('credit.management.commands.fix_stuck_credits.mark_credited')
    def test_many_matching_credits(self, mocked_mark_credited):
        self.mock_uncredited_credits()
        with responses.RequestsMock() as rsps:
            self.mock_nomis_response(rsps, matching_count=2)
            call_command('fix_stuck_credits', self.sample_prison, self.sample_date, self.sample_username)

        self.assertCreditNotLinked(mocked_mark_credited)

    @mock.patch('credit.management.commands.fix_stuck_credits.input', new=lambda _: 'y')  # not prompted
    @mock.patch('credit.management.commands.fix_stuck_credits.mark_credited')
    def test_no_matching_credits(self, mocked_mark_credited):
        self.mock_uncredited_credits()
        with responses.RequestsMock() as rsps:
            self.mock_nomis_response(rsps, matching_count=0)
            call_command('fix_stuck_credits', self.sample_prison, self.sample_date, self.sample_username)

        self.assertCreditNotLinked(mocked_mark_credited)
