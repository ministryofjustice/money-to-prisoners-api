import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
import jwt
from mtp_common.test_utils import silence_logger

from core.models import Token
from core.views import UpdateNOMISTokenView

User = get_user_model()


class TokenTestCase(TestCase):
    def assertAccessiblyOnlyBySuperuser(self, url, sentinel):  # noqa
        response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=302)

        user_details = dict(username='a_user', password='a_user')
        user = User.objects.create_user(**user_details)

        self.client.login(**user_details)
        response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=302)

        user.is_staff = True
        user.save()
        self.client.login(**user_details)
        with silence_logger('django.request'):
            response = self.client.get(url)
        self.assertNotContains(response, sentinel, status_code=403)

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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_ec_key = generate_private_key(SECP256R1, default_backend())

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

        token = jwt.encode({
            'key': 'abc',
        }, key=self.private_ec_key, algorithm='ES256').decode()
        self.client.post(url, data={'token': ContentFile(token)})
        self.assertEqual(Token.objects.get(name='nomis').token, token)

        token = jwt.encode({
            'key': 'abc',
            'iat': time.time() + 1000,
        }, key=self.private_ec_key, algorithm='ES256').decode()
        response = self.client.post(url, data={'token': ContentFile(token)})
        self.assertFormError(response, 'form', 'token', ['Token is not yet valid'])
        self.assertNotEqual(Token.objects.get(name='nomis').token, token)

        token = jwt.encode({
            'key': 'abc',
            'exp': time.time() - 1000,
        }, key=self.private_ec_key, algorithm='ES256').decode()
        response = self.client.post(url, data={'token': ContentFile(token)})
        self.assertFormError(response, 'form', 'token', ['Token has already expired'])
        self.assertNotEqual(Token.objects.get(name='nomis').token, token)

        token = jwt.encode({
            'key': 'abc',
            'access': ['^some-url$'],
            'iat': time.time() - 1000,
            'exp': time.time() + 1000,
        }, key=self.private_ec_key, algorithm='ES256').decode()
        self.client.post(url, data={'token': ContentFile(token)})
        self.assertEqual(Token.objects.get(name='nomis').token, token)
        response = self.client.get(url)
        self.assertContains(response, '^some-url$')
