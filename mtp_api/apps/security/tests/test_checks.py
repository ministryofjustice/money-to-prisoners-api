import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from model_mommy import mommy
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from mtp_auth.tests.mommy_recipes import basic_user
from mtp_auth.tests.utils import AuthTestCaseMixin
from notification.rules import RULES
from notification.tests.utils import (
    make_sender, make_prisoner,
    make_csfreq_credits, make_csnum_credits, make_cpnum_credits,
)
from payment.models import Payment, PAYMENT_STATUS
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import (
    Check, CHECK_STATUS, CheckAutoAcceptRule,
    PrisonerProfile, SenderProfile,
)
from security.tests.utils import (
    generate_checks,
    generate_sender_profiles_from_payments,
    generate_prisoner_profiles_from_prisoner_locations
)
from transaction.tests.utils import generate_transactions

User = get_user_model()


class CheckTestCase(APITestCase, AuthTestCaseMixin):
    """
    Tests related to the Check model.
    """
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json'
    ]

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be accepted.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        user = basic_user.make()
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
        )

        check.accept(by=user)
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_at, mocked_now())
        self.assertEqual(check.actioned_by, user)

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check_with_reason(self, mocked_now):
        """
        Test that a pending check can be accepted.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        user = basic_user.make()
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
        )
        reason = 'A good reason'

        check.accept(by=user, reason=reason)
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.decision_reason, reason)

    @mock.patch('security.models.now')
    def test_can_accept_an_accepted_check(self, mocked_now):
        """
        Test that accepting an already accepted check doesn't do anything.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.ACCEPTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
        )

        check.accept(by=user)
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertNotEqual(check.actioned_at, mocked_now())

    @mock.patch('security.models.now')
    def test_cannot_accept_a_rejected_check(self, mocked_now):
        """
        Test that accepting a rejected check raises ValidationError.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.REJECTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
        )

        with self.assertRaises(ValidationError):
            check.accept(by=user)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertNotEqual(check.actioned_at, mocked_now())

    @mock.patch('security.models.now')
    def test_can_reject_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be rejected.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        user = basic_user.make()
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
            rejection_reasons={'payment_source_linked_other_prisoners': True}
        )
        reason = 'Some reason'

        check.reject(by=user, reason=reason, rejection_reasons={'payment_source_linked_other_prisoners': True})
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_at, mocked_now())
        self.assertEqual(check.actioned_by, user)
        self.assertEqual(check.decision_reason, reason)

    @mock.patch('security.models.now')
    def test_can_reject_a_rejected_check(self, mocked_now):
        """
        Test that rejected an already rejected check doesn't do anything.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.REJECTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
            decision_reason='Some old reason',
            rejection_reasons={'payment_source_linked_other_prisoners': True}
        )
        reason = 'Some reason'

        check.reject(by=user, reason=reason, rejection_reasons={'payment_source_multiple_cards': True})
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertEqual(check.rejection_reasons, {'payment_source_linked_other_prisoners': True})
        self.assertNotEqual(check.actioned_at, mocked_now())
        self.assertNotEqual(check.decision_reason, reason)

    def test_empty_rejection_reason_raises_error(self):
        """
        Test that rejecting a check without reason raises ValidationError.
        """
        users = make_test_users(clerks_per_prison=1)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
        )

        # Execute
        response = self.client.post(
            reverse('security-check-reject', kwargs={'pk': check.id}),
            {
                'decision_reason': 'thisshouldntmatter',
                'rejection_reasons': {
                }
            },
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(users['security_fiu_users'][0])
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {'rejection_reasons': ['This field cannot be blank.']},
        )

    @mock.patch('security.models.now')
    def test_cannot_reject_an_accepted_check(self, mocked_now):
        """
        Test that rejecting an accepted check raises ValidationError.
        """
        mocked_now.return_value = timezone.make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.ACCEPTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
        )
        reason = 'Some reason'

        with self.assertRaises(ValidationError) as e:
            check.reject(by=user, reason=reason, rejection_reasons={'payment_source_linked_other_prisoners': True})

        self.assertEqual(
            e.exception.message_dict,
            {'status': ['Cannot reject an accepted check.']},
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertNotEqual(check.actioned_at, mocked_now())

    def test_can_reject_check_with_rejection_reason(self):
        # Setup
        users = make_test_users(clerks_per_prison=1)
        prisoner_locations = load_random_prisoner_locations()
        generate_payments(payment_batch=50)
        generate_prisoner_profiles_from_prisoner_locations(prisoner_locations)
        generate_sender_profiles_from_payments(number_of_senders=1, reassign_dcsd=True)
        generate_checks(number_of_checks=1, create_invalid_checks=False, overrides={'status': 'pending'})
        check = Check.objects.filter(status='pending').first()

        # Execute
        response = self.client.post(
            reverse('security-check-reject', kwargs={'pk': check.id}),
            {
                'decision_reason': 'computer says no',
                'rejection_reasons': {
                    'payment_source_linked_other_prisoners': True,
                }
            },
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(users['security_fiu_users'][0])
        )

        # Assert Response
        self.assertEqual(response.status_code, 204)

        # Assert State Change
        check.refresh_from_db()
        self.assertEqual(check.rejection_reasons, {'payment_source_linked_other_prisoners': True})
        self.assertEqual(check.decision_reason, 'computer says no')

    def test_cannot_accept_check_with_rejection_reason(self):
        # Setup
        users = make_test_users(clerks_per_prison=1)
        prisoner_locations = load_random_prisoner_locations()
        generate_payments(payment_batch=50)
        generate_prisoner_profiles_from_prisoner_locations(prisoner_locations)
        generate_sender_profiles_from_payments(number_of_senders=1, reassign_dcsd=True)
        generate_checks(number_of_checks=1, create_invalid_checks=False, overrides={'status': 'pending'})
        check = Check.objects.filter(status='pending').first()

        # Execute
        response = self.client.post(
            reverse('security-check-accept', kwargs={'pk': check.id}),
            {
                'decision_reason': 'computer says no',
                'rejection_reasons': {
                    'payment_source_linked_other_prisoners': True,
                }
            },
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(users['security_fiu_users'][0])
        )

        # Assert Response
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {'non_field_errors': ['You cannot give rejection reasons when accepting a check']}
        )

        # Assert Lack of State Change
        check.refresh_from_db()
        self.assertEqual(check.status, 'pending')
        self.assertEqual(check.rejection_reasons, {})
        self.assertEqual(check.decision_reason, '')


class CreditCheckTestCase(TestCase):
    """
    Tests related to creating checks for credits
    """
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def test_will_not_check_non_initial_credits(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments()

        for credit in Credit.objects.credit_pending():
            self.assertFalse(credit.should_check())
        for credit in Credit.objects.credited():
            self.assertFalse(credit.should_check())

    def test_will_not_check_transactions(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_transactions(consistent_history=True)

        for credit in Credit.objects.credit_pending():
            self.assertFalse(credit.should_check())
        for credit in Credit.objects.credited():
            self.assertFalse(credit.should_check())
        for credit in Credit.objects.refund_pending():
            self.assertFalse(credit.should_check())
        for credit in Credit.objects.refunded():
            self.assertFalse(credit.should_check())

    def test_will_not_check_non_pending_payments(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(10)
        credit = Credit.objects.credited().first()
        credit.owner = None
        credit.resolution = CREDIT_RESOLUTION.INITIAL
        credit.payment.status = PAYMENT_STATUS.FAILED
        credit.save()
        self.assertFalse(credit.should_check())

    def _make_candidate_credit(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(10)
        call_command('update_security_profiles')
        credit = Credit.objects.credited().first()
        credit.owner = None
        credit.resolution = CREDIT_RESOLUTION.INITIAL
        payment = credit.payment
        payment.status = PAYMENT_STATUS.PENDING
        credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
        return credit

    def test_will_not_check_credits_with_incomplete_details(self):
        credit = self._make_candidate_credit()
        payment = credit.payment
        payment.card_number_first_digits = None
        payment.card_number_last_digits = None
        payment.card_expiry_date = None
        payment.cardholder_name = None
        payment.card_brand = None
        self.assertFalse(credit.should_check())

    def test_credit_checked_with_no_matching_rules(self):
        credit = self._make_candidate_credit()
        self.assertTrue(credit.should_check())
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(len(check.description), 1)
        self.assertIn('automatically accepted', check.description[0])
        self.assertFalse(check.rules)

    def test_credit_without_profiles_checked_with_matched_rules(self):
        credit = self._make_candidate_credit()
        prisoner_profile = PrisonerProfile.objects.get_for_credit(credit)
        sender_profile = SenderProfile.objects.get_for_credit(credit)
        fiu_group = Group.objects.get(name='FIU')
        fiu_user = fiu_group.user_set.first()
        prisoner_profile.monitoring_users.add(fiu_user)
        sender_profile.debit_card_details.first().monitoring_users.add(fiu_user)
        self.assertTrue(credit.should_check())
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.PENDING)
        self.assertEqual(len(check.description), 2)
        description = '\n'.join(check.description)
        self.assertIn('FIU prisoners', description)
        self.assertIn('FIU payment sources', description)
        self.assertListEqual(sorted(check.rules), ['FIUMONP', 'FIUMONS'])

    def test_credit_with_profiles_checked_with_matched_rules(self):
        credit = self._make_candidate_credit()
        prisoner_profile = PrisonerProfile.objects.get_for_credit(credit)
        sender_profile = SenderProfile.objects.get_for_credit(credit)
        credit.prisoner_profile = prisoner_profile
        credit.sender_profile = sender_profile
        fiu_group = Group.objects.get(name='FIU')
        fiu_user = fiu_group.user_set.first()
        prisoner_profile.monitoring_users.add(fiu_user)
        sender_profile.debit_card_details.first().monitoring_users.add(fiu_user)
        self.assertTrue(credit.should_check())
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.PENDING)
        self.assertEqual(len(check.description), 2)
        description = '\n'.join(check.description)
        self.assertIn('FIU prisoners', description)
        self.assertIn('FIU payment sources', description)
        self.assertListEqual(sorted(check.rules), ['FIUMONP', 'FIUMONS'])

    def test_credit_with_matched_csfreq_rule(self):
        rule = RULES['CSFREQ']
        count = rule.kwargs['limit'] + 1
        credit_list = make_csfreq_credits(timezone.now(), make_sender(), count)
        credit = credit_list[0]
        check = Check.objects.create_for_credit(credit)
        self.assertListEqual(check.rules, ['CSFREQ'])

    def test_credit_with_matched_csnum_rule(self):
        rule = RULES['CSNUM']
        count = rule.kwargs['limit'] + 1
        credit_list = make_csnum_credits(timezone.now(), make_prisoner(), count)
        credit = credit_list[0]
        check = Check.objects.create_for_credit(credit)
        self.assertListEqual(check.rules, ['CSNUM'])

    def test_credit_with_matched_cpnum_rule(self):
        rule = RULES['CPNUM']
        count = rule.kwargs['limit'] + 1
        credit_list = make_cpnum_credits(timezone.now(), make_sender(), count)
        credit = credit_list[0]
        check = Check.objects.create_for_credit(credit)
        # credits matching CPNUM will always CSFREQ currently
        self.assertListEqual(sorted(check.rules), ['CPNUM', 'CSFREQ'])


class AutomaticCreditCheckTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        self.send_money_user = Group.objects.get(name='SendMoney').user_set.first()

    def test_check_created_automatically(self):
        """
        Ensures that a payment created and updated by send-money will automatically create a check
        """
        auth_header = self.get_http_authorization_for_user(self.send_money_user)
        new_payment = {
            'amount': 1255,
            'service_charge': 0,
            'recipient_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '1989-01-21',
            'ip_address': '127.0.0.1',
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment,
            format='json', HTTP_AUTHORIZATION=auth_header,
        )
        payment = response.json()
        self.assertQuerysetEqual(Check.objects.filter(credit__payment__uuid=payment['uuid']), [])

        payment_update = {
            'email': 'sender@outside.local',
            'worldpay_id': '12345',
            'cardholder_name': 'Mary Halls',
            'card_number_first_digits': '111122',
            'card_number_last_digits': '8888',
            'card_expiry_date': '10/20',
            'card_brand': 'Visa',
            'billing_address': {
                'line1': '62 Petty France',
                'line2': '',
                'city': 'London',
                'country': 'UK',
                'postcode': 'SW1H 9EU'
            },
        }
        response = self.client.patch(
            reverse('payment-detail', args=[payment['uuid']]), data=payment_update,
            format='json', HTTP_AUTHORIZATION=auth_header,
        )
        payment = response.json()
        payment = Payment.objects.get(uuid=payment['uuid'])
        self.assertEqual(payment.status, PAYMENT_STATUS.PENDING)
        self.assertEqual(payment.credit.resolution, CREDIT_RESOLUTION.INITIAL)
        self.assertTrue(hasattr(payment.credit, 'security_check'))
        self.assertEqual(payment.credit.security_check.status, CHECK_STATUS.ACCEPTED)

    def test_pending_check_created_for_monitored_user(self):
        """
        Ensures that a payment updated by send-money will automatically create a pending check for monitored prisoner
        """
        fiu_group = Group.objects.get(name='FIU')
        fiu_user = fiu_group.user_set.first()
        prisoner_profile, _ = PrisonerProfile.objects.get_or_create(prisoner_number='A1409AE')
        prisoner_profile.monitoring_users.add(fiu_user)
        prisoner_profile.save()

        auth_header = self.get_http_authorization_for_user(self.send_money_user)
        new_payment = {
            'amount': 1255,
            'service_charge': 0,
            'recipient_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '1989-01-21',
            'ip_address': '127.0.0.1',
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment,
            format='json', HTTP_AUTHORIZATION=auth_header,
        )
        payment = response.json()
        self.assertQuerysetEqual(Check.objects.filter(credit__payment__uuid=payment['uuid']), [])

        payment_update = {
            'email': 'sender@outside.local',
            'worldpay_id': '12345',
            'cardholder_name': 'Mary Halls',
            'card_number_first_digits': '111122',
            'card_number_last_digits': '8888',
            'card_expiry_date': '10/20',
            'card_brand': 'Visa',
            'billing_address': {
                'line1': '62 Petty France',
                'line2': '',
                'city': 'London',
                'country': 'UK',
                'postcode': 'SW1H 9EU'
            },
        }
        response = self.client.patch(
            reverse('payment-detail', args=[payment['uuid']]), data=payment_update,
            format='json', HTTP_AUTHORIZATION=auth_header,
        )
        payment = response.json()
        payment = Payment.objects.get(uuid=payment['uuid'])
        self.assertEqual(payment.status, PAYMENT_STATUS.PENDING)
        self.assertEqual(payment.credit.resolution, CREDIT_RESOLUTION.INITIAL)
        self.assertTrue(hasattr(payment.credit, 'security_check'))
        self.assertEqual(payment.credit.security_check.status, CHECK_STATUS.PENDING)


class AutoAcceptRuleTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.users = make_test_users(clerks_per_prison=1)
        prisoner_locations = load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(payment_batch=1)
        prisoner_profiles = generate_prisoner_profiles_from_prisoner_locations(prisoner_locations)
        sender_profiles = generate_sender_profiles_from_payments(number_of_senders=1, reassign_dcsd=True)
        prisoner_profiles[0].monitoring_users.add(self.users['security_fiu_users'][0].id)
        sender_profiles[0].debit_card_details.first().monitoring_users.add(self.users['security_fiu_users'][0].id)

        response = self.client.post(
            reverse(
                'security-check-auto-accept-list'
            ),
            data={
                'prisoner_profile_id': prisoner_profiles[0].id,
                'debit_card_sender_details_id': sender_profiles[0].debit_card_details.first().id,
                'states': [
                    {
                        'reason': 'This person has amazing hair',
                    }
                ]
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.users['security_fiu_users'][0]),
        )
        self.assertEqual(response.status_code, 201)
        self.auto_accept_rule = CheckAutoAcceptRule.objects.get(id=response.json()['id'])

    def test_payment_for_pair_with_active_auto_accept_progresses_immediately(self):
        # Set up
        payments = generate_payments(
            payment_batch=1,
            overrides={
                'credit': {
                    'prisoner_profile_id': self.auto_accept_rule.prisoner_profile_id,
                    'sender_profile_id': self.auto_accept_rule.debit_card_sender_details.sender.id
                }
            }
        )
        credit = payments[0].credit

        # Call
        check = Check.objects.create_for_credit(credit)

        # Assert
        self.assertEqual(check.auto_accept_rule_state, self.auto_accept_rule.get_latest_state())
        self.assertEqual(check.rules, ['FIUMONP', 'FIUMONS'])
        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)

    def test_payment_for_pair_with_inactive_auto_accept_caught_by_delayed_capture(self):
        self.client.patch(
            reverse(
                'security-check-auto-accept-detail',
                args=[self.auto_accept_rule.id]
            ),
            data={
                'states': [
                    {
                        'active': False,
                        'reason': 'Ignore that they cut off their hair',
                    }
                ]
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.users['security_fiu_users'][0]),
        )
        payments = generate_payments(
            payment_batch=1,
            overrides={
                'credit': {
                    'prisoner_profile_id': self.auto_accept_rule.prisoner_profile_id,
                    'sender_profile_id': self.auto_accept_rule.debit_card_sender_details.sender.id
                }
            }
        )
        credit = payments[0].credit

        # Call
        check = Check.objects.create_for_credit(credit)

        # Assert
        self.assertEqual(check.auto_accept_rule_state, None)
        self.assertEqual(check.rules, ['FIUMONP', 'FIUMONS'])
        self.assertEqual(check.status, CHECK_STATUS.PENDING)

    def test_payment_where_sender_not_on_auto_accept_caught_by_delayed_capture(self):
        sender_profile_id = SenderProfile.objects.exclude(
            id=self.auto_accept_rule.debit_card_sender_details.sender.id
        ).first().id
        payments = generate_payments(
            payment_batch=1,
            overrides={
                'credit': {
                    'prisoner_profile_id': self.auto_accept_rule.prisoner_profile_id,
                    'sender_profile_id': sender_profile_id
                }
            }
        )
        credit = payments[0].credit

        # Call
        check = Check.objects.create_for_credit(credit)

        # Assert
        self.assertEqual(check.auto_accept_rule_state, None)
        self.assertEqual(check.rules, ['FIUMONP'])
        self.assertEqual(check.status, CHECK_STATUS.PENDING)

    def test_payment_where_prisoner_not_on_auto_accept_caught_by_delayed_capture(self):
        prisoner_profile_id = PrisonerProfile.objects.exclude(
            id=self.auto_accept_rule.prisoner_profile_id
        ).first().id
        payments = generate_payments(
            payment_batch=1,
            overrides={
                'credit': {
                    'prisoner_profile_id': prisoner_profile_id,
                    'sender_profile_id': self.auto_accept_rule.debit_card_sender_details.sender.id
                }
            }
        )
        credit = payments[0].credit

        # Call
        check = Check.objects.create_for_credit(credit)

        # Assert
        self.assertEqual(check.auto_accept_rule_state, None)
        self.assertEqual(check.rules, ['FIUMONS'])
        self.assertEqual(check.status, CHECK_STATUS.PENDING)
