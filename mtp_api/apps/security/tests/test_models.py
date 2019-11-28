import datetime
from unittest import mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import make_aware
from model_mommy import mommy

from core.tests.utils import make_test_users
from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from mtp_auth.tests.mommy_recipes import basic_user
from payment.models import PAYMENT_STATUS
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import (
    Check, CHECK_STATUS,
    PrisonerProfile, SenderProfile,
)
from transaction.tests.utils import generate_transactions


class CheckTestCase(TestCase):
    """
    Tests related to the Check model.
    """

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be accepted.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

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
    def test_can_accept_an_accepted_check(self, mocked_now):
        """
        Test that accepting an already accepted check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

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
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

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
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        user = basic_user.make()
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
        )
        reason = 'Some reason'

        check.reject(by=user, reason=reason)
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_at, mocked_now())
        self.assertEqual(check.actioned_by, user)
        self.assertEqual(check.rejection_reason, reason)

    @mock.patch('security.models.now')
    def test_can_reject_a_rejected_check(self, mocked_now):
        """
        Test that rejected an already rejected check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.REJECTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
            rejection_reason='Some old reason',
        )
        reason = 'Some reason'

        check.reject(by=user, reason=reason)
        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertNotEqual(check.actioned_at, mocked_now())
        self.assertNotEqual(check.rejection_reason, reason)

    def test_empty_reason_raises_error(self):
        """
        Test that rejecting a check without reason raises ValidationError.
        """
        user = basic_user.make()
        check = mommy.make(
            Check,
            status=CHECK_STATUS.PENDING,
            actioned_at=None,
            actioned_by=None,
        )

        with self.assertRaises(ValidationError) as e:
            check.reject(by=user, reason='')

        self.assertEqual(
            e.exception.message_dict,
            {'reason': ['This field cannot be blank.']},
        )

    @mock.patch('security.models.now')
    def test_cannot_reject_an_accepted_check(self, mocked_now):
        """
        Test that rejecting an accepted check raises ValidationError.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        existing_check_user, user = basic_user.make(_quantity=2)
        check = mommy.make(
            Check,
            status=CHECK_STATUS.ACCEPTED,
            actioned_at=mocked_now() - datetime.timedelta(days=1),
            actioned_by=existing_check_user,
        )
        reason = 'Some reason'

        with self.assertRaises(ValidationError) as e:
            check.reject(by=user, reason=reason)

        self.assertEqual(
            e.exception.message_dict,
            {'status': ['Cannot reject an accepted check.']},
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, existing_check_user)
        self.assertNotEqual(check.actioned_at, mocked_now())


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
            self.assertFalse(Check.objects.should_check_credit(credit))
        for credit in Credit.objects.credited():
            self.assertFalse(Check.objects.should_check_credit(credit))

    def test_will_not_check_transactions(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_transactions(consistent_history=True)

        for credit in Credit.objects.credit_pending():
            self.assertFalse(Check.objects.should_check_credit(credit))
        for credit in Credit.objects.credited():
            self.assertFalse(Check.objects.should_check_credit(credit))
        for credit in Credit.objects.refund_pending():
            self.assertFalse(Check.objects.should_check_credit(credit))
        for credit in Credit.objects.refunded():
            self.assertFalse(Check.objects.should_check_credit(credit))

    def test_will_not_check_non_pending_payments(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(10)
        credit = Credit.objects.credited().first()
        credit.owner = None
        credit.resolution = CREDIT_RESOLUTION.INITIAL
        credit.payment.status = PAYMENT_STATUS.FAILED
        credit.save()
        self.assertFalse(Check.objects.should_check_credit(credit))

    def _make_candidate_credit(self):
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_payments(10)
        call_command('update_security_profiles')
        credit = Credit.objects.credited().first()
        credit.prisoner_profile = None
        credit.sender_profile = None
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
        self.assertFalse(Check.objects.should_check_credit(credit))

    def test_credit_checked_with_no_matching_rules(self):
        credit = self._make_candidate_credit()
        self.assertTrue(Check.objects.should_check_credit(credit))
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertIn('automatically accepted', check.description)
        self.assertFalse(check.rules)

    def test_credit_without_profiles_checked_with_matched_rules(self):
        credit = self._make_candidate_credit()
        prisoner_profile = PrisonerProfile.objects.get_for_credit(credit)
        sender_profile = SenderProfile.objects.get_for_credit(credit)
        fiu_group = Group.objects.get(name='FIU')
        fiu_user = fiu_group.user_set.first()
        prisoner_profile.monitoring_users.add(fiu_user)
        sender_profile.debit_card_details.first().monitoring_users.add(fiu_user)
        self.assertTrue(Check.objects.should_check_credit(credit))
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.PENDING)
        self.assertIn('matched FIU monitoring rules', check.description)
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
        self.assertTrue(Check.objects.should_check_credit(credit))
        check = Check.objects.create_for_credit(credit)
        self.assertEqual(check.status, CHECK_STATUS.PENDING)
        self.assertIn('matched FIU monitoring rules', check.description)
        self.assertListEqual(sorted(check.rules), ['FIUMONP', 'FIUMONS'])
