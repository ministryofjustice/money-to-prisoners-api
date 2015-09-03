from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications

from prison.models import Prison


class UserViewTestCase(APITestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]

    def setUp(self):
        super(UserViewTestCase, self).setUp()
        self.users, _, _, _ = make_test_users(clerks_per_prison=2)
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
        logged_in_user = self.users[0]
        self.client.force_authenticate(user=logged_in_user)

        for user in self.users[1:]:
            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_access_my_data(self):
        for user in self.users:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)
            self.assertEqual(
                response.data['prisons'],
                [prison.pk for prison in user.prisonusermapping.prisons.all()]
            )
