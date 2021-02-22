import datetime
from unittest import mock
from pprint import pformat

import dictdiffer
from django.urls import reverse
from django.utils.timezone import make_aware, now
from model_mommy import mommy
from parameterized import parameterized
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import format_date_or_datetime, make_test_users, create_security_fiu_user
from credit.models import Credit
from credit.constants import CREDIT_RESOLUTION
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import CHECK_STATUS
from security.models import (
    Check,
    CheckAutoAcceptRule,
    CheckAutoAcceptRuleState,
    PrisonerProfile,
    SenderProfile,
)
from security.tests.utils import (
    generate_sender_profiles_from_payments,
    generate_prisoner_profiles_from_prisoner_locations
)


class BaseCheckTestCase(APITestCase, AuthTestCaseMixin):
    """
    Base TestCase for security check endpoints.
    """
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(num_security_fiu_users=2)
        self.prison_clerks = test_users['prison_clerks']
        self.security_fiu_users = test_users['security_fiu_users']
        load_random_prisoner_locations()
        generate_payments(payment_batch=100, days_of_history=5)
        self.generate_checks()

    def generate_checks(self):
        # create a pending check for each credit in initial state
        for credit in Credit.objects_all.filter(resolution=CREDIT_RESOLUTION.INITIAL):
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.PENDING,
                rules=['ABC', 'DEF'],
                description=['Failed rules'],
            )

        for credit in Credit.objects_all.filter(resolution=CREDIT_RESOLUTION.FAILED):
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.REJECTED,
                rules=['ABC', 'DEF'],
                description=['Failed rules'],
                actioned_at=now(),
                actioned_by=self.security_fiu_users[0],
                decision_reason='because...',
                rejection_reasons={'payment_source_linked_other_prisoners': True}
            )

        for credit in Credit.objects.all():
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.ACCEPTED,
                rules=['ABC', 'DEF'],
                description=['Failed rules'],
                actioned_at=now(),
                actioned_by=self.security_fiu_users[0],
            )

    def _get_unauthorised_application_user(self):
        return self.prison_clerks[0]

    def _get_authorised_user(self):
        return self.security_fiu_users[0]

    def assertCheckEqual(self, expected_check, actual_check_data):  # noqa: N802
        expected_data_item = {
            'id': expected_check.pk,
            'description': expected_check.description,
            'rules': expected_check.rules,
            'status': expected_check.status,
            'credit': {
                'id': expected_check.credit.id,
                'amount': expected_check.credit.amount,
                'anonymous': actual_check_data['credit']['anonymous'],
                'billing_address': {
                    'id': expected_check.credit.billing_address.pk,
                    'city': expected_check.credit.billing_address.city,
                    'country': expected_check.credit.billing_address.country,
                    'debit_card_sender_details': expected_check.credit.billing_address.debit_card_sender_details,
                    'line1': expected_check.credit.billing_address.line1,
                    'line2': expected_check.credit.billing_address.line2,
                    'postcode': expected_check.credit.billing_address.postcode,
                } if expected_check.credit.billing_address else None,
                'card_expiry_date': expected_check.credit.card_expiry_date,
                'card_number_first_digits': expected_check.credit.card_number_first_digits,
                'card_number_last_digits': expected_check.credit.card_number_last_digits,
                'comments': [],
                'credited_at': format_date_or_datetime(expected_check.credit.credited_at),
                'intended_recipient': expected_check.credit.intended_recipient,
                'ip_address': expected_check.credit.ip_address,
                'nomis_transaction_id': expected_check.credit.nomis_transaction_id,
                'owner': expected_check.credit.owner.pk if expected_check.credit.owner else None,
                'owner_name': expected_check.credit.owner_name,
                'prison': expected_check.credit.prison.nomis_id,
                'prison_name': expected_check.credit.prison.name,
                'prisoner_name': expected_check.credit.prisoner_name,
                'prisoner_number': expected_check.credit.prisoner_number,
                'prisoner_profile': expected_check.credit.prisoner_profile_id,
                'received_at': format_date_or_datetime(expected_check.credit.received_at),
                'reconciliation_code': expected_check.credit.reconciliation_code,
                'refunded_at': None,
                'resolution': expected_check.credit.resolution,
                'reviewed': False,
                'sender_account_number': None,
                'sender_email': expected_check.credit.sender_email,
                'sender_name': expected_check.credit.sender_name,
                'sender_profile': expected_check.credit.sender_profile_id,
                'sender_roll_number': None,
                'sender_sort_code': None,
                'set_manual_at': None,
                'short_payment_ref': actual_check_data['credit']['short_payment_ref'],
                'source': expected_check.credit.source,
                'started_at': format_date_or_datetime(expected_check.credit.payment.created),
            },
            'actioned_at': format_date_or_datetime(expected_check.actioned_at),
            'actioned_by': expected_check.actioned_by.pk if expected_check.actioned_by else None,
            'actioned_by_name': actual_check_data['actioned_by_name'],
            'assigned_to': expected_check.assigned_to.pk if expected_check.assigned_to else None,
            'assigned_to_name': actual_check_data['assigned_to_name'],
            'decision_reason': expected_check.decision_reason if expected_check.decision_reason else '',
            'rejection_reasons': (
                expected_check.rejection_reasons if expected_check.status == CHECK_STATUS.REJECTED else {}
            ),
            'auto_accept_rule_state': {
                'added_by': expected_check.auto_accept_rule_state.added_by,
                'reason': expected_check.auto_accept_rule_state.reason,
                'created': expected_check.auto_accept_rule_state.created,
                'auto_accept_rule': expected_check.auto_accept_rule_state.auto_accept_rule.pk,
            } if expected_check.auto_accept_rule_state else None
        }
        assert expected_data_item == actual_check_data, pformat(
            list(dictdiffer.diff(expected_data_item, actual_check_data))
        )


class CheckListTestCase(BaseCheckTestCase):
    """
    Tests related to getting security checks.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.get(
            reverse('security-check-list'),
            {},
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_get_all_checks(self):
        """
        Test that the list endpoint returns all checks paginated if no filter is passed in.
        """
        filters = {}

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['count'], Credit.objects_all.count())

        actual_data_item = response_data['results'][0]
        check = Check.objects.get(pk=actual_data_item['id'])

        self.assertCheckEqual(check, actual_data_item)

    def test_get_checks_in_pending(self):
        """
        Test that the list endpoint only returns the checks in pending if a filter is passed in.
        """
        filters = {
            'status': CHECK_STATUS.PENDING,
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            Check.objects.filter(status=CHECK_STATUS.PENDING).count(),
        )
        for item in response_data['results']:
            self.assertEqual(item['status'], CHECK_STATUS.PENDING)

    def test_get_checks_for_specific_rule(self):
        """
        Test that the list endpoint only returns the checks in pending if a filter is passed in.
        """
        filters = {
            'rules': 'ABC',
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            Check.objects.all().count(),
        )
        for item in response_data['results']:
            self.assertIn('ABC', item['rules'])

        filters = {
            'rules': 'XYZ',
        }

        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            0,
        )

    def test_check_filtering_by_started_at(self):
        """
        Test that the list endpoint can filter by payment creation date.
        """
        credits_started_at = list(Check.objects.all().order_by('credit__payment__created').values_list(
            'credit__payment__created', flat=True
        ))
        check_count = len(credits_started_at)
        earliest_check = credits_started_at[0].isoformat()
        latest_check = credits_started_at[-1].isoformat()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())

        def assertCheckCount(filters, expected_count):  # noqa: N802
            response = self.client.get(
                reverse('security-check-list'),
                filters,
                format='json',
                HTTP_AUTHORIZATION=auth,
            )
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)
            response_data = response.json()
            self.assertEqual(
                response_data['count'],
                expected_count,
            )

        assertCheckCount(
            {
                'started_at__lt': earliest_check,
            },
            0
        )
        assertCheckCount(
            {
                'started_at__gte': earliest_check,
            },
            check_count
        )
        assertCheckCount(
            {
                'started_at__lt': latest_check,
            },
            check_count - 1
        )

    def test_check_filtering_by_credit_resolution(self):
        """
        Test that the list endpoint can filter by credit resolution.
        """
        # change one check.credit to test that it shouldn't get included in the response
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()
        check.credit.resolution = CREDIT_RESOLUTION.FAILED
        check.credit.save()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            {
                'credit_resolution': CREDIT_RESOLUTION.INITIAL,
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            response.json()['count'],
            Check.objects.filter(status=CHECK_STATUS.PENDING).count() - 1,
        )

    def test_check_filtering_by_actioned_by(self):
        """
        Test that the list endpoint only returns the checks with an actioned_by id.
        """
        filters = {
            'actioned_by': True,
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()

        self.assertEqual(
            response_data['count'],
            Check.objects.filter(actioned_by__isnull=False).count(),
        )

        for item in response_data['results']:
            self.assertIsNotNone(item['actioned_by'])


class PatchCheckTestCase(BaseCheckTestCase):
    """
    Tests related to patching security checks.
    """

    def test_patch(self):
        """
        Tests related to patching a single security check.
        """
        check = Check.objects.first()
        assigned_to_user = self.security_fiu_users[0]

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        actual_check_data = response.json()
        self.assertEqual(actual_check_data['assigned_to'], assigned_to_user.id)
        self.assertEqual(actual_check_data['assigned_to_name'], assigned_to_user.get_full_name())

        check = Check.objects.get(pk=actual_check_data['id'])
        self.assertCheckEqual(check, actual_check_data)

    def test_patch_fails_on_when_already_assigned(self):
        """
        Tests related to patching a single security check.
        """
        check = Check.objects.first()
        assigned_to_user = self.security_fiu_users[0]
        new_assigned_to_user = self.security_fiu_users[1]

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        actual_check_data = response.json()

        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': new_assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

        # Assert check unchanged
        self.assertEqual(actual_check_data['assigned_to'], assigned_to_user.id)
        self.assertEqual(actual_check_data['assigned_to_name'], assigned_to_user.get_full_name())

        check = Check.objects.get(pk=actual_check_data['id'])
        self.assertCheckEqual(check, actual_check_data)

    def test_patch_succeeds_after_removal_of_assignment(self):
        """
        Tests related to patching a single security check.
        """
        check = Check.objects.first()
        assigned_to_user = self.security_fiu_users[0]
        new_assigned_to_user = self.security_fiu_users[1]

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': None
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': new_assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        actual_check_data = response.json()
        self.assertEqual(actual_check_data['assigned_to'], new_assigned_to_user.id)
        self.assertEqual(actual_check_data['assigned_to_name'], new_assigned_to_user.get_full_name())

        check = Check.objects.get(pk=actual_check_data['id'])
        self.assertCheckEqual(check, actual_check_data)

    def test_patch_fails_on_when_patching_read_only_field(self):
        """
        Tests related to patching a single security check.
        """
        check = Check.objects.first()
        assigned_to_user = self.security_fiu_users[0]

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'assigned_to': assigned_to_user.id
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        actual_check_data = response.json()

        assert check.status != CHECK_STATUS.ACCEPTED
        response = self.client.patch(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            data={
                'status': CHECK_STATUS.ACCEPTED
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        # Assert check unchanged
        self.assertEqual(actual_check_data['assigned_to'], assigned_to_user.id)
        self.assertEqual(actual_check_data['assigned_to_name'], assigned_to_user.get_full_name())

        check = Check.objects.get(pk=actual_check_data['id'])
        self.assertCheckEqual(check, actual_check_data)


class GetCheckTestCase(BaseCheckTestCase):
    """
    Tests related to getting a single security check.
    """

    def test_get(self):
        """
        Test that the get object endpoint returns check details.
        """
        check = Check.objects.first()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        actual_check_data = response.json()
        self.assertCheckEqual(check, actual_check_data)

    def test_get_assigned_check(self):
        """
        Test that the get object endpoint returns check details including assignment
        """
        check = Check.objects.first()
        check.assigned_to = self.security_fiu_users[0]
        check.save()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        actual_check_data = response.json()
        self.assertCheckEqual(check, actual_check_data)

    def test_get_check_auto_accept_rule_state_attached(self):
        """
        Test that the get object endpoint returns CheckAutoAcceptRuleState when appropriate
        """
        # Setup
        response = self.client.post(
            reverse(
                'security-check-auto-accept-list'
            ),
            data={
                'prisoner_profile_id': PrisonerProfile.objects.first().id,
                'debit_card_sender_details_id': SenderProfile.objects.first().debit_card_details.first().id,
                'states': [
                    {
                        'reason': 'This person has amazing hair',
                    }
                ]
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self._get_authorised_user()),
        )
        self.assertEqual(response.status_code, 201)
        auto_accept_rule = CheckAutoAcceptRule.objects.get(id=response.json()['id'])
        payments = generate_payments(
            payment_batch=1,
            overrides={
                'credit': {
                    'prisoner_profile_id': auto_accept_rule.prisoner_profile_id,
                    'sender_profile_id': auto_accept_rule.debit_card_sender_details.sender.id
                }
            },
            reconcile_payments=False
        )
        credit = payments[0].credit
        check = Check.objects.create_for_credit(credit)

        # Call
        response = self.client.get(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self._get_authorised_user()),
        )

        # Assert
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        actual_check_data = response.json()
        self.assertCheckEqual(check, actual_check_data)


class AcceptCheckTestCase(BaseCheckTestCase):
    """
    Tests related to accepting a check.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be accepted.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 4, 1))

        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, authorised_user)
        self.assertEqual(check.actioned_at, mocked_now())

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check_with_empty_rejection_reasons(self, mocked_now):
        """
        Test that a pending check can be accepted if payload contains empty rejection reasons
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 4, 1))

        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
                'rejection_reasons': {},
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, authorised_user)
        self.assertEqual(check.actioned_at, mocked_now())

    @mock.patch('security.models.now')
    def test_can_accept_an_accepted_check(self, mocked_now):
        """
        Test that accepting an already accepted check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        check = Check.objects.filter(status=CHECK_STATUS.ACCEPTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertNotEqual(check.actioned_at, mocked_now())

    def test_cannot_accept_a_rejected_check(self):
        """
        Test that accepting a rejected check returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.REJECTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'status': ['Cannot accept a rejected check.'],
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)


class RejectCheckTestCase(BaseCheckTestCase):
    """
    Tests related to rejecting a check.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': 'Some reason',
                'rejection_reasons': {'payment_source_linked_other_prisoners': True}
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @mock.patch('security.models.now')
    def test_can_reject_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be rejected.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 4, 1))

        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        reason = 'Some reason'
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': reason,
                'rejection_reasons': {'payment_source_linked_other_prisoners': True}
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_by, authorised_user)
        self.assertEqual(check.actioned_at, mocked_now())
        self.assertEqual(check.decision_reason, reason)

    @mock.patch('security.models.now')
    def test_can_reject_a_rejected_check(self, mocked_now):
        """
        Test that rejected an already rejected check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        check = Check.objects.filter(status=CHECK_STATUS.REJECTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        reason = 'some reason'
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': reason,
                'rejection_reasons': {'payment_source_linked_other_prisoners': True}
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertNotEqual(check.actioned_at, mocked_now())
        self.assertNotEqual(check.decision_reason, reason)

    def test_empty_rejection_reason_raises_error(self):
        """
        Test that rejecting a check without rejection_reason returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            {
                'decision_reason': 'thisdoesntmatter',
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'rejection_reasons': ['This field is required.']
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.PENDING)

    def test_cannot_reject_an_accepted_check(self):
        """
        Test that rejecting a pending check returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.ACCEPTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            {
                'decision_reason': 'some reason',
                'rejection_reasons': {'payment_source_linked_other_prisoners': True}
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'status': ['Cannot reject an accepted check.'],
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)


class CheckAutoAcceptRuleViewTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.users = make_test_users(num_security_fiu_users=2)
        self.added_by_user = self.users['security_fiu_users'][0]
        self.updated_by_user = self.users['security_fiu_users'][1]

        prisoner_locations = load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(payment_batch=2)

        self.prisoner_profile = generate_prisoner_profiles_from_prisoner_locations(prisoner_locations)[0]
        self.sender_profile, other_sender_profile = generate_sender_profiles_from_payments(
            number_of_senders=2, reassign_dcsd=True
        )
        self.debit_card_sender_details = self.sender_profile.debit_card_details.first()
        self.other_debit_card_sender_details = other_sender_profile.debit_card_details.first()

    def _create_auto_accept(
        self, prisoner_profile_id, debit_card_sender_details_id, reason, user, auto_accept_created=None,
        auto_accept_state_created=None, expected_status_code=201
    ):
        response = self.client.post(
            reverse(
                'security-check-auto-accept-list'
            ),
            data={
                'prisoner_profile_id': prisoner_profile_id,
                'debit_card_sender_details_id': debit_card_sender_details_id,
                'states': [
                    {
                        'reason': reason
                    }
                ]
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, expected_status_code)
        # Fix datetime as we can't easily mock this
        payload = response.json()
        if expected_status_code == 201:
            auto_accept_payload_id = payload['id']
            check_auto_accept = CheckAutoAcceptRule.objects.get(id=auto_accept_payload_id)
            if auto_accept_created:
                check_auto_accept.created = format_date_or_datetime(auto_accept_created)
                check_auto_accept.save()

            if auto_accept_state_created:
                check_auto_accept_state = check_auto_accept.states.first()
                check_auto_accept_state.created = format_date_or_datetime(auto_accept_state_created)
                check_auto_accept_state.save()
        return payload

    def _update_auto_accept(self, auto_accept_rule_id, reason, user, active=False, auto_accept_state_created=None):
        patch_response = self.client.patch(
            reverse(
                'security-check-auto-accept-detail',
                args=[auto_accept_rule_id]
            ),
            data={
                'states': [
                    {
                        'active': active,
                        'reason': reason
                    }
                ]
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(patch_response.status_code, 200)
        actual_response = patch_response.json()

        if auto_accept_state_created:
            auto_accept_payload_id = actual_response['id']
            check_auto_accept = CheckAutoAcceptRule.objects.get(id=auto_accept_payload_id)
            check_auto_accept_state = check_auto_accept.states.order_by('-created').first()
            check_auto_accept_state.created = format_date_or_datetime(auto_accept_state_created)
            check_auto_accept_state.save()

        self.assertIn('id', list(actual_response.keys()))
        del actual_response['id']
        self.assertIn('created', list(actual_response.keys()))
        del actual_response['created']
        for state in actual_response['states']:
            self.assertIn('created', list(state.keys()))
            del state['created']
            self.assertIn('auto_accept_rule', list(state.keys()))
            del state['auto_accept_rule']

        return actual_response

    def _list_auto_accept(
        self, url, user, strip_id=True, strip_created=True, strip_states_auto_accept_rule=True,
        strip_states_created=True
    ):
        get_response = self.client.get(
            url,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )

        # Assert
        self.assertEqual(get_response.status_code, 200)
        actual_response = get_response.json()

        for result in actual_response['results']:
            self.assertIn('id', list(result.keys()))
            if strip_id:
                del result['id']
            self.assertIn('created', list(result.keys()))
            if strip_created:
                del result['created']
            for state in result['states']:
                self.assertIn('auto_accept_rule', list(state.keys()))
                if strip_states_auto_accept_rule:
                    del state['auto_accept_rule']
                self.assertIn('created', list(state.keys()))
                if strip_states_created:
                    del state['created']
        return actual_response

    @staticmethod
    def _prisoner_profile_to_api_dict(prisoner_profile):
        return {
            'created': format_date_or_datetime(prisoner_profile.created),
            'credit_count': 0,
            'credit_total': 0,
            'current_prison': {
                'name': prisoner_profile.current_prison.name,
                'nomis_id': prisoner_profile.current_prison.nomis_id,
            },
            'disbursement_count': 0,
            'disbursement_total': 0,
            'id': prisoner_profile.id,
            'modified': format_date_or_datetime(prisoner_profile.modified),
            'prisoner_dob': prisoner_profile.prisoner_dob.isoformat(),
            'prisoner_name': prisoner_profile.prisoner_name,
            'prisoner_number': prisoner_profile.prisoner_number,
            'prisons': [],
            'provided_names': []
        }

    @staticmethod
    def _debit_card_sender_details_to_api_dict(debit_card_sender_details):
        return {
            'card_expiry_date': debit_card_sender_details.card_expiry_date,
            'card_number_last_digits': debit_card_sender_details.card_number_last_digits,
            'cardholder_names': [],
            'postcode': debit_card_sender_details.postcode,
            'sender': debit_card_sender_details.id,
            'sender_emails': []
        }

    def test_auto_accept_rule_create(self):
        expected_response = {
            'prisoner_profile': self._prisoner_profile_to_api_dict(
                self.prisoner_profile
            ),
            'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                self.debit_card_sender_details
            ),
            'states': [
                {
                    'active': True,
                    'reason': 'they have amazing hair',
                    'added_by': {
                        'first_name': self.added_by_user.first_name,
                        'last_name': self.added_by_user.last_name,
                        'username': self.added_by_user.username,
                    }
                }
            ]
        }
        actual_response = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user
        )

        self.assertIn('id', list(actual_response.keys()))
        del actual_response['id']
        self.assertIn('created', list(actual_response.keys()))
        del actual_response['created']
        self.assertIn('created', list(actual_response['states'][0].keys()))
        del actual_response['states'][0]['created']
        self.assertIn('auto_accept_rule', list(actual_response['states'][0].keys()))
        del actual_response['states'][0]['auto_accept_rule']
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )
        self.assertEqual(CheckAutoAcceptRule.objects.count(), 1)
        auto_accept_rule = CheckAutoAcceptRule.objects.first()
        self.assertEqual(auto_accept_rule.prisoner_profile_id, self.prisoner_profile.id)
        self.assertEqual(auto_accept_rule.debit_card_sender_details_id, self.debit_card_sender_details.id)
        self.assertEqual(auto_accept_rule.get_latest_state().reason, 'they have amazing hair')
        self.assertEqual(auto_accept_rule.get_latest_state().added_by_id, self.added_by_user.id)
        self.assertEqual(auto_accept_rule.is_active(), True)

    def test_auto_accept_rule_create_collision(self):
        # Setup
        expected_response = {
            'non_field_errors': [
                'An existing AutoAcceptRule is present for this DebitCardSenderDetails/PrisonerProfile pair'
            ]
        }

        self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user
        )

        # Call
        actual_response = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='Oh I know, dont they just',
            user=self.added_by_user,
            expected_status_code=400
        )

        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )
        self.assertEqual(CheckAutoAcceptRule.objects.count(), 1)

    def test_auto_accept_rule_deactivate(self):
        # Setup
        expected_response = {
            'prisoner_profile': self._prisoner_profile_to_api_dict(
                self.prisoner_profile
            ),
            'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                self.debit_card_sender_details
            ),
            'states': [
                {
                    'active': True,
                    'reason': 'they have amazing hair',
                    'added_by': {
                        'first_name': self.added_by_user.first_name,
                        'last_name': self.added_by_user.last_name,
                        'username': self.added_by_user.username,
                    }
                },
                {
                    'active': False,
                    'reason': 'they have shaved it off',
                    'added_by': {
                        'first_name': self.updated_by_user.first_name,
                        'last_name': self.updated_by_user.last_name,
                        'username': self.updated_by_user.username,
                    }
                }
            ]
        }
        auto_accept_rule = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user
        )

        # Call
        actual_response = self._update_auto_accept(
            auto_accept_rule_id=auto_accept_rule['id'],
            active=False,
            reason='they have shaved it off',
            user=self.updated_by_user
        )

        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )
        self.assertEqual(CheckAutoAcceptRule.objects.count(), 1)
        self.assertEqual(CheckAutoAcceptRuleState.objects.count(), 2)
        auto_accept_rule = CheckAutoAcceptRule.objects.first()
        self.assertEqual(auto_accept_rule.get_latest_state().reason, 'they have shaved it off')
        self.assertEqual(auto_accept_rule.get_latest_state().added_by_id, self.updated_by_user.id)
        self.assertEqual(auto_accept_rule.is_active(), False)

    def test_auto_accept_rule_reactivate(self):
        # Setup
        expected_response = {
            'prisoner_profile': self._prisoner_profile_to_api_dict(
                self.prisoner_profile
            ),
            'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                self.debit_card_sender_details
            ),
            'states': [
                {
                    'active': True,
                    'reason': 'they have amazing hair',
                    'added_by': {
                        'first_name': self.added_by_user.first_name,
                        'last_name': self.added_by_user.last_name,
                        'username': self.added_by_user.username,
                    }
                },
                {
                    'active': False,
                    'reason': 'they have shaved it off',
                    'added_by': {
                        'first_name': self.updated_by_user.first_name,
                        'last_name': self.updated_by_user.last_name,
                        'username': self.updated_by_user.username,
                    }
                },
                {
                    'active': True,
                    'reason': 'they grew it back again',
                    'added_by': {
                        'first_name': self.updated_by_user.first_name,
                        'last_name': self.updated_by_user.last_name,
                        'username': self.updated_by_user.username,
                    }
                }
            ]
        }
        auto_accept_rule = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user
        )
        self._update_auto_accept(
            auto_accept_rule_id=auto_accept_rule['id'],
            active=False,
            reason='they have shaved it off',
            user=self.updated_by_user
        )

        # Call
        actual_response = self._update_auto_accept(
            auto_accept_rule_id=auto_accept_rule['id'],
            active=True,
            reason='they grew it back again',
            user=self.updated_by_user
        )

        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )
        self.assertEqual(CheckAutoAcceptRule.objects.count(), 1)
        self.assertEqual(CheckAutoAcceptRuleState.objects.count(), 3)
        auto_accept_rule = CheckAutoAcceptRule.objects.first()
        self.assertEqual(auto_accept_rule.get_latest_state().reason, 'they grew it back again')
        self.assertEqual(auto_accept_rule.get_latest_state().added_by_id, self.updated_by_user.id)
        self.assertEqual(auto_accept_rule.is_active(), True)

    def test_auto_accept_rule_list(self):
        # Setup
        expected_response = {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [{
                'prisoner_profile': self._prisoner_profile_to_api_dict(
                    self.prisoner_profile
                ),
                'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                    self.debit_card_sender_details
                ),
                'states': [
                    {
                        'active': True,
                        'reason': 'they have amazing hair',
                        'added_by': {
                            'first_name': self.added_by_user.first_name,
                            'last_name': self.added_by_user.last_name,
                            'username': self.added_by_user.username,
                        }
                    }
                ]
            }]
        }

        post_response_payload = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user
        )

        expected_response['results'][0]['states'][0]['auto_accept_rule'] = post_response_payload['id']
        # Call
        actual_response = self._list_auto_accept(
            url=reverse(
                'security-check-auto-accept-list'
            ),
            user=self.updated_by_user,
            strip_states_auto_accept_rule=False
        )
        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )

    @parameterized.expand([
        ('states__added_by__last_name', 0, 1),
        ('-states__added_by__last_name', 1, 0),
        ('states__created', 1, 0),
        ('-states__created', 0, 1),
    ])
    def test_auto_accept_rule_list_ordering(self, querystring, first_index, second_index):
        # Setup
        datetime_now = datetime.datetime.now()
        other_user = create_security_fiu_user(
            name_and_password='security-fiu-2', first_name='Aardvark', last_name='Zebraington'
        )
        possible_results = [
            {
                'prisoner_profile': self._prisoner_profile_to_api_dict(
                    self.prisoner_profile
                ),
                'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                    self.debit_card_sender_details
                ),
                'created': format_date_or_datetime(datetime_now - datetime.timedelta(hours=4)),
                'states': [
                    {
                        'active': True,
                        'reason': 'they have amazing hair',
                        'added_by': {
                            'first_name': self.added_by_user.first_name,
                            'last_name': self.added_by_user.last_name,
                            'username': self.added_by_user.username,
                        },
                        'created': format_date_or_datetime(datetime_now - datetime.timedelta(hours=1))
                    }
                ]
            },
            {
                'prisoner_profile': self._prisoner_profile_to_api_dict(
                    self.prisoner_profile
                ),
                'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                    self.other_debit_card_sender_details
                ),
                'created': format_date_or_datetime(datetime_now - datetime.timedelta(hours=3)),
                'states': [
                    {
                        'active': True,
                        'reason': 'they have an amazing beard',
                        'added_by': {
                            'first_name': other_user.first_name,
                            'last_name': other_user.last_name,
                            'username': other_user.username,
                        },
                        'created': format_date_or_datetime(datetime_now - datetime.timedelta(hours=2))
                    }
                ]
            }
        ]
        expected_response = {
            'count': 2,
            'next': None,
            'previous': None,
            'results': [
                possible_results[first_index],
                possible_results[second_index],
            ]
        }

        self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user,
            auto_accept_created=datetime_now - datetime.timedelta(hours=4),
            auto_accept_state_created=datetime_now - datetime.timedelta(hours=1)
        )

        self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.other_debit_card_sender_details.id,
            reason='they have an amazing beard',
            user=other_user,
            auto_accept_created=datetime_now - datetime.timedelta(hours=3),
            auto_accept_state_created=datetime_now - datetime.timedelta(hours=2)
        )

        # Call
        actual_response = self._list_auto_accept(
            url='{}?ordering={}'.format(
                reverse(
                    'security-check-auto-accept-list',
                ),
                querystring
            ),
            user=self.updated_by_user,
            strip_created=False,
            strip_states_created=False
        )

        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )

    def test_auto_accept_rule_list_filter_is_active(self):
        # Setup
        datetime_now = datetime.datetime.now()
        expected_response = {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [{
                'prisoner_profile': self._prisoner_profile_to_api_dict(
                    self.prisoner_profile
                ),
                'debit_card_sender_details': self._debit_card_sender_details_to_api_dict(
                    self.debit_card_sender_details
                ),
                'states': [
                    {
                        'active': True,
                        'reason': 'they have amazing hair',
                        'added_by': {
                            'first_name': self.added_by_user.first_name,
                            'last_name': self.added_by_user.last_name,
                            'username': self.added_by_user.username,
                        }
                    }
                ],
            }]
        }

        self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.debit_card_sender_details.id,
            reason='they have amazing hair',
            user=self.added_by_user,
            auto_accept_created=datetime_now - datetime.timedelta(hours=4),
            auto_accept_state_created=datetime_now - datetime.timedelta(hours=1)
        )

        other_check_auto_accept = self._create_auto_accept(
            prisoner_profile_id=self.prisoner_profile.id,
            debit_card_sender_details_id=self.other_debit_card_sender_details.id,
            reason='they have an amazing beard',
            user=self.added_by_user,
            auto_accept_created=datetime_now - datetime.timedelta(hours=3),
            auto_accept_state_created=datetime_now - datetime.timedelta(hours=2)
        )

        self._update_auto_accept(
            auto_accept_rule_id=other_check_auto_accept['id'],
            active=False,
            reason='they shaved it off',
            user=self.updated_by_user,
            auto_accept_state_created=datetime_now - datetime.timedelta(hours=1)
        )

        # Execute
        actual_response = self._list_auto_accept(
            '{}?is_active=true'.format(
                reverse(
                    'security-check-auto-accept-list'
                )
            ),
            user=self.updated_by_user
        )

        # Assert
        self.assertDictEqual(
            expected_response,
            actual_response,
            msg=pformat(
                list(dictdiffer.diff(expected_response, actual_response))
            )
        )
