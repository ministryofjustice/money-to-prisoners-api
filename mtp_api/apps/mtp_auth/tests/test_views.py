from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications

from prison.models import Prison

from mtp_auth.models import PrisonUserMapping


class UserViewTestCase(APITestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]

    def setUp(self):
        super(UserViewTestCase, self).setUp()
        (
            self.prison_clerks, self.prisoner_location_admins,
            self.bank_admins, self.refund_bank_admins
        ) = make_test_users(clerks_per_prison=2)
        self.test_users = (
            self.prison_clerks + self.prisoner_location_admins +
            self.bank_admins + self.refund_bank_admins
        )

        self.prisons = Prison.objects.all()
        make_test_oauth_applications()

    def _get_url(self, username):
        return reverse('user-detail', kwargs={'username': username})

    def test_cannot_access_data_when_not_logged_in(self):
        url = self._get_url('me')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_others_data(self):
        """
        Returns 404 when trying to access other's user data.
        404 because we don't want to leak anything about our
        db.
        """
        logged_in_user = self.prison_clerks[0]
        self.client.force_authenticate(user=logged_in_user)

        for user in self.prison_clerks[1:]:
            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_access_my_data_including_managing_prisons(self):
        for user in self.prison_clerks:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)
            prison_ids = list(user.prisonusermapping.prisons.values_list('pk', flat=True))
            self.assertEqual(response.data['prisons'], prison_ids)

    def test_correct_permissions_returned(self):
        for user in self.test_users:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['permissions'], user.get_all_permissions())

    def test_my_data_with_empty_prisons(self):
        users = \
            self.prisoner_location_admins + \
            self.bank_admins + self.refund_bank_admins

        for user in users:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)
            self.assertEqual(response.data['prisons'], [])
