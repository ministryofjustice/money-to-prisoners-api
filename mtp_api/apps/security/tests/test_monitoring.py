from django.urls import reverse
from rest_framework import status as http_status

from security.models import SenderProfile, PrisonerProfile, RecipientProfile
from security.tests.test_views import SecurityViewTestCase


class MonitoringTestMixin:
    profile = NotImplemented
    url_prefix = NotImplemented

    def get_monitored_object(self, profile):
        return profile

    def test_start_monitoring(self):
        profile = self.profile.objects.last()
        url = reverse('%s-monitor' % self.url_prefix, args=[profile.id])
        user = self._get_authorised_user()

        response = self.client.post(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        self.assertTrue(
            user in
            self.get_monitored_object(
                self.profile.objects.get(id=profile.id)
            ).monitoring_users.all()
        )

    def test_stop_monitoring(self):
        profile = self.profile.objects.last()
        url = reverse('%s-unmonitor' % self.url_prefix, args=[profile.id])
        user = self._get_authorised_user()

        self.get_monitored_object(profile).monitoring_users.add(user)

        response = self.client.post(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        self.assertTrue(
            user not in
            self.get_monitored_object(
                self.profile.objects.get(id=profile.id)
            ).monitoring_users.all()
        )


class SenderMonitoringTestCase(MonitoringTestMixin, SecurityViewTestCase):
    profile = SenderProfile
    url_prefix = 'senderprofile'

    def get_monitored_object(self, profile):
        bank_details = profile.bank_transfer_details.first()
        card_details = profile.debit_card_details.first()
        if bank_details:
            return bank_details.sender_bank_account
        elif card_details:
            return card_details


class PrisonerMonitoringTestCase(MonitoringTestMixin, SecurityViewTestCase):
    profile = PrisonerProfile
    url_prefix = 'prisonerprofile'


class RecipientMonitoringTestCase(MonitoringTestMixin, SecurityViewTestCase):
    profile = RecipientProfile
    url_prefix = 'recipientprofile'

    def get_monitored_object(self, profile):
        bank_details = profile.bank_transfer_details.first()
        if bank_details:
            return bank_details.recipient_bank_account
