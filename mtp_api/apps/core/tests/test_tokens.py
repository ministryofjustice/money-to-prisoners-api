import itertools
import time

from cryptography.hazmat.backends import default_backend as get_cryptography_backend
from cryptography.hazmat.primitives.asymmetric import ec as elliptic_curves
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
import jwt
from mtp_common.test_utils import silence_logger
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.models import Token
from core.tests.utils import make_test_users
from core.views import UpdateNOMISTokenView
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID
from mtp_auth.tests.utils import AuthTestCaseMixin

User = get_user_model()


class TokenTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_ec_key = elliptic_curves.generate_private_key(
            elliptic_curves.SECP256R1,
            get_cryptography_backend()
        )

    def make_client_token(self, payload):
        return jwt.encode(payload, key=self.private_ec_key, algorithm='ES256').decode()

    def assertAccessiblyOnlyBySuperuser(self, url, sentinel):  # noqa
        response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=http_status.HTTP_302_FOUND)

        user_details = dict(username='a_user', password='a_user')
        user = User.objects.create_user(**user_details)

        self.client.login(**user_details)
        response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=http_status.HTTP_302_FOUND)

        user.is_staff = True
        user.save()
        self.client.login(**user_details)
        with silence_logger('django.request'):
            response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=http_status.HTTP_403_FORBIDDEN)

        user.is_superuser = True
        user.save()
        self.client.login(**user_details)
        response = self.client.get(url)
        self.assertContains(response, sentinel)


@override_settings(NOMIS_API_PUBLIC_KEY='\n-----BEGIN PUBLIC KEY-----\n???\n-----END PUBLIC KEY-----')
class DownloadPublicKeyTestCase(TokenTestCase):
    def test_download(self):
        url = reverse('admin:download_public_key')
        self.assertAccessiblyOnlyBySuperuser(url, 'BEGIN PUBLIC KEY')


class UpdateNOMISToken(TokenTestCase):
    def test_access(self):
        url = reverse('admin:update_nomis_token')
        self.assertAccessiblyOnlyBySuperuser(url, UpdateNOMISTokenView.title)

    def test_update_token(self):
        url = reverse('admin:update_nomis_token')

        user_details = dict(username='a_user', password='a_user')
        User.objects.create_user(is_staff=True, is_superuser=True, **user_details)
        self.client.login(**user_details)

        response = self.client.post(url, data={'token': ContentFile(b'1234.1234.1234')})
        self.assertFormError(response, 'form', 'token', ['Invalid client token'])
        self.assertEqual(Token.objects.count(), 0)

        token = self.make_client_token({
            'key': 'abc',
        })
        self.client.post(url, data={'token': ContentFile(token)})
        self.assertEqual(Token.objects.get(name='nomis').token, token)

        token = self.make_client_token({
            'key': 'abc',
            'iat': time.time() + 1000,
        })
        response = self.client.post(url, data={'token': ContentFile(token)})
        self.assertFormError(response, 'form', 'token', ['Token is not yet valid'])
        self.assertNotEqual(Token.objects.get(name='nomis').token, token)

        token = self.make_client_token({
            'key': 'abc',
            'exp': time.time() - 1000,
        })
        response = self.client.post(url, data={'token': ContentFile(token)})
        self.assertFormError(response, 'form', 'token', ['Token has already expired'])
        self.assertNotEqual(Token.objects.get(name='nomis').token, token)

        token = self.make_client_token({
            'key': 'abc',
            'access': ['^some-url$'],
            'iat': time.time() - 1000,
            'exp': time.time() + 1000,
        })
        self.client.post(url, data={'token': ContentFile(token)})
        self.assertEqual(Token.objects.get(name='nomis').token, token)
        response = self.client.get(url)
        self.assertContains(response, '^some-url$')


class TokenRetrievalTestCase(APITestCase, AuthTestCaseMixin, TokenTestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']
    allowed_clients = (CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID)

    def setUp(self):
        super().setUp()
        self.url = reverse('token-detail', kwargs={'pk': 'nomis'})
        self.normal_users = make_test_users(clerks_per_prison=1)
        self.token = self.make_client_token({
            'key': 'abc',
            'access': ['^some-url$'],
            'iat': time.time() - 1000,
            'exp': time.time() + 1000,
        })
        Token.objects.create(name='nomis', token=self.token)

    def test_unauthenticated_forbidden(self):
        response = self.client.get(self.url, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn(self.token, response.content.decode())

    def test_normal_users_forbidden(self):
        for normal_user in itertools.chain.from_iterable(self.normal_users.values()):
            authorisation = self.get_http_authorization_for_user(normal_user)
            response = self.client.get(self.url, format='json', HTTP_AUTHORIZATION=authorisation)
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
            self.assertNotIn(self.token, response.content.decode())

    def test_token_retrieval(self):
        user = User.objects.create_user(username='a_user', password='a_user')
        user.user_permissions.add(
            Permission.objects.get_by_natural_key('view_token', 'core', 'token')
        )
        user.save()
        for client_id in self.allowed_clients:
            authorisation = self.get_http_authorization_for_user(user, client_id=client_id)
            response = self.client.get(self.url, format='json', HTTP_AUTHORIZATION=authorisation)
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)
            self.assertJSONEqual(response.content.decode(), {
                'token': self.token,
                'expires': None,
            })
