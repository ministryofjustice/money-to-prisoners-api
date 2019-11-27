import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.timezone import make_aware
from model_mommy import mommy

from mtp_auth.tests.mommy_recipes import basic_user
from security.constants import CHECK_STATUS
from security.models import Check


class CheckTestCase(TestCase):
    """
    Tests related to the Check model.
    """
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

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
