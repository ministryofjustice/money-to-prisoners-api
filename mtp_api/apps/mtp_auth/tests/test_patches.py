import logging
from unittest import mock

from django.urls import reverse
from mtp_common.test_utils import silence_logger
from oauth2_provider.models import Application
from oauthlib.oauth2 import InvalidRequestError, InvalidGrantError, UnsupportedGrantTypeError

from core.tests.utils import make_test_users
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID
from mtp_auth.tests.test_views import AuthBaseTestCase


class OauthTokenRequestPatchTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_test_users(clerks_per_prison=1, num_security_fiu_users=0)['prison_clerks'][0]
        self.cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

    def try_login(self):
        with silence_logger('django.request', level=logging.ERROR):
            return self.client.post(
                reverse('oauth2_provider:token'),
                {
                    # this would be successful unless mocked
                    'grant_type': 'password',
                    'username': self.user.username,
                    'password': self.user.username,
                    'client_id': self.cashbook_client.client_id,
                    'client_secret': self.cashbook_client.client_id,  # NB: client_secret is hashed
                }
            )

    @mock.patch('mtp_auth.validators.ApplicationRequestValidator.validate_user')
    def test_invalid_grant_with_invalid_credentials_401(self, mocked_validate_user):
        # pretends that username/password were wrong: status code SHOULD be modified back to 401

        mocked_validate_user.return_value = False
        response = self.try_login()
        self.assertEqual(response.status_code, 401)
        response_data = response.json()
        self.assertEqual(response_data['error'], 'invalid_grant')
        self.assertIn('Invalid credentials', response_data['error_description'])

    @mock.patch('oauthlib.oauth2.ResourceOwnerPasswordCredentialsGrant.validate_token_request')
    def test_invalid_grant_with_other_problem_still_400(self, mocked_token_request):
        # pretends that request was malformed: status code should NOT be modified remaining 400

        mocked_token_request.side_effect = UnsupportedGrantTypeError()
        response = self.try_login()
        self.assertEqual(response.status_code, 400)

        mocked_token_request.side_effect = InvalidGrantError()
        response = self.try_login()
        self.assertEqual(response.status_code, 400)

        mocked_token_request.side_effect = InvalidRequestError('Request is missing client_secret parameter.')
        response = self.try_login()
        self.assertEqual(response.status_code, 400)
