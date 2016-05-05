from oauth2_provider.models import AccessToken
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from prison.models import Prison
from credit.models import Credit
from credit.constants import CREDIT_STATUS, CREDIT_RESOLUTION
from transaction.tests.utils import generate_transactions, latest_transaction_date


class BaseCreditViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]
    STATUS_FILTERS = {
        None: lambda t: True,
        CREDIT_STATUS.LOCKED: lambda t: t.owner and not t.credited,
        CREDIT_STATUS.AVAILABLE: lambda t: not t.owner and not t.credited,
        CREDIT_STATUS.CREDITED: lambda t: t.owner and t.credited
    }
    transaction_batch = 50

    def setUp(self):
        super(BaseCreditViewTestCase, self).setUp()
        (
            self.prison_clerks, self.prisoner_location_admins,
            self.bank_admins, self.refund_bank_admins,
            self.send_money_users,
        ) = make_test_users(clerks_per_prison=2)

        self.latest_transaction_date = latest_transaction_date()
        self.credits = [t.credit for t in generate_transactions(
            transaction_batch=self.transaction_batch
        ) if t.credit]
        self.prisons = Prison.objects.all()

    def _get_locked_credits_qs(self, prisons, user=None):
        params = {
            'resolution': CREDIT_RESOLUTION.PENDING,
            'prison__in': prisons
        }
        if user:
            params['owner'] = user
        else:
            params['owner__isnull'] = False

        return Credit.objects.filter(**params)

    def _get_available_credits_qs(self, prisons):
        return Credit.objects.filter(
            owner__isnull=True, resolution=CREDIT_RESOLUTION.PENDING,
            prison__in=prisons
        )

    def _get_credited_credits_qs(self, prisons, user=None):
        return Credit.objects.filter(
            owner=user, resolution=CREDIT_RESOLUTION.CREDITED, prison__in=prisons
        )

    def _get_latest_date(self):
        return self.latest_transaction_date.date()


class CreditRejectsRequestsWithoutPermissionTestMixin(object):

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
        for user, http_auth_header in users_data:
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