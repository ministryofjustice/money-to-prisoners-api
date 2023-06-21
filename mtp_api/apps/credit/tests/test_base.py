from datetime import datetime, time

from django.db import models
from django.utils import timezone
from oauth2_provider.models import AccessToken
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.constants import CreditResolution, CreditStatus
from credit.models import Credit
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID
from mtp_auth.models import PrisonUserMapping
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments, latest_payment_date
from prison.models import Prison
from prison.tests.utils import load_random_prisoner_locations
from transaction.tests.utils import generate_transactions, latest_transaction_date


class BaseCreditViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json',
    ]
    STATUS_FILTERS = {
        None: lambda c: True,
        CreditStatus.credit_pending.value: lambda c: (
            c.prison and
            (c.resolution == CreditResolution.pending.value or
             c.resolution == CreditResolution.manual.value) and
            not c.blocked
        ),
        CreditStatus.credited.value: lambda c: c.credited,
    }
    transaction_batch = 100

    def setUp(self):
        super().setUp()

        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        self.security_staff = test_users['security_staff']

        self.latest_transaction_date = latest_transaction_date()
        self.latest_payment_date = latest_payment_date()
        load_random_prisoner_locations()
        transaction_credits = [t.credit for t in generate_transactions(
            transaction_batch=self.transaction_batch, days_of_history=5
        ) if t.credit]
        payment_credits = [p.credit for p in generate_payments(
            payment_batch=self.transaction_batch, days_of_history=5
        ) if p.credit and p.credit.resolution != 'initial']
        self.credits = transaction_credits + payment_credits
        self.prisons = Prison.objects.all()

    def _get_queryset(self, user, prisons):
        qs = Credit.objects.filter(prison__in=prisons)
        if user and (user.applicationusermapping_set.first().application.client_id ==
                     CASHBOOK_OAUTH_CLIENT_ID):
            return qs.filter(
                received_at__lt=timezone.make_aware(
                    datetime.combine(timezone.now(), time.min)
                )
            )
        return qs

    def _get_credit_pending_credits_qs(self, prisons, user):
        return self._get_queryset(user, prisons).filter(
            blocked=False, resolution=CreditResolution.pending,
        )

    def _get_credited_credits_qs(self, prisons, user):
        return self._get_queryset(user, prisons).filter(
            owner=user, resolution=CreditResolution.credited, prison__in=prisons,
        )

    def _get_latest_date(self):
        return Credit.objects.all().aggregate(models.Max('received_at'))['received_at__max']

    def _get_managed_prison_credits(self, logged_in_user=None):
        credits = self.credits
        logged_in_user = logged_in_user or self._get_authorised_user()
        if logged_in_user.has_perm('credit.view_any_credit'):
            return credits
        else:
            if (
                logged_in_user.applicationusermapping_set.first().application.client_id == CASHBOOK_OAUTH_CLIENT_ID
            ):
                credits = [
                    c
                    for c in credits
                    if c.received_at
                    and c.received_at < datetime.combine(timezone.now().date(), time.min).replace(tzinfo=timezone.utc)
                ]
            managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))
            return [c for c in credits if c.prison in managing_prisons]


class CreditRejectsRequestsWithoutPermissionTestMixin:
    """
    Mixin for permission checks on the endpoint.

    It expects `_get_url(user, prison)`, `_get_unauthorised_application_users()`
    and `_get_authorised_user()` instance methods defined.
    """
    ENDPOINT_VERB = 'get'

    def _get_url(self, *args, **kwargs):
        raise NotImplementedError()

    def _get_unauthorised_application_users(self):
        raise NotImplementedError()

    def _get_unauthorised_user(self):
        user = self._get_authorised_user()
        user.groups.first().permissions.all().delete()
        return user

    def _get_authorised_user(self):
        raise NotImplementedError()

    def test_fails_without_application_permissions(self):
        """
        Tests that if the user logs in via a different application,
        they won't be able to access the API.
        """
        # constructing list of unauthorised users+application
        unauthorised_users = self._get_unauthorised_application_users()
        users_data = [
            (user, self.get_http_authorization_for_user(user))
            for user in unauthorised_users
        ]

        # + valid user logged in using a different oauth application
        authorised_user = self._get_authorised_user()

        invalid_client_id = AccessToken.objects.filter(
            user=unauthorised_users[0]
        ).first().application.client_id

        users_data.append(
            (
                authorised_user,
                self.get_http_authorization_for_user(authorised_user, invalid_client_id)
            )
        )

        url = self._get_url()
        for _, http_auth_header in users_data:
            verb_callable = getattr(self.client, self.ENDPOINT_VERB)
            response = verb_callable(
                url, format='json',
                HTTP_AUTHORIZATION=http_auth_header
            )

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_fails_without_action_permissions(self):
        """
        Tests that if the user does not have permissions,
        they won't be able to access the API.
        """
        user = self._get_unauthorised_user()

        url = self._get_url()

        verb_callable = getattr(self.client, self.ENDPOINT_VERB)
        response = verb_callable(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
