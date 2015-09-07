from oauth2_provider.models import AccessToken

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications
from mtp_auth.tests.utils import AuthTestCaseMixin

from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS

from .utils import generate_transactions


class BaseTransactionViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]
    STATUS_FILTERS = {
        None: lambda t: True,
        TRANSACTION_STATUS.LOCKED: lambda t: t.owner and not t.credited,
        TRANSACTION_STATUS.AVAILABLE: lambda t: not t.owner and not t.credited,
        TRANSACTION_STATUS.CREDITED: lambda t: t.owner and t.credited
    }
    transaction_batch = 50

    def setUp(self):
        super(BaseTransactionViewTestCase, self).setUp()
        (
            self.prison_clerks, self.prisoner_location_admins, self.bank_admins,
            self.refund_bank_admins
        ) = make_test_users(clerks_per_prison=2)

        self.transactions = generate_transactions(
            transaction_batch=self.transaction_batch
        )
        self.prisons = Prison.objects.all()
        make_test_oauth_applications()

    def _get_locked_transactions_qs(self, prisons, user=None):
        params = {
            'credited': False,
            'prison__in': prisons
        }
        if user:
            params['owner'] = user
        else:
            params['owner__isnull'] = False

        return Transaction.objects.filter(**params)

    def _get_available_transactions_qs(self, prisons):
        return Transaction.objects.filter(
            owner__isnull=True, credited=False, prison__in=prisons
        )

    def _get_credited_transactions_qs(self, prisons, user=None):
        return Transaction.objects.filter(
            owner=user, credited=True, prison__in=prisons
        )


class TransactionRejectsRequestsWithoutPermissionTestMixin(object):

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
        Tests that if the user does not have permissions to create
        transactions, they won't be able to access the API.
        """
        user = self._get_unauthorised_user()

        url = self._get_url()

        verb_callable = getattr(self.client, self.ENDPOINT_VERB)
        response = verb_callable(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
