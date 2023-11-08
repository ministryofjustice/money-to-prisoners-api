from django.db.models import Count, Q
from django.urls import reverse
from rest_framework import status as http_status

from disbursement.constants import DisbursementResolution, DisbursementMethod
from disbursement.models import Disbursement
from security.models import RecipientProfile
from security.tests.test_views import SecurityViewTestCase


class RecipientProfileListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('recipientprofile-list')

    def test_filter_by_prisoner_count(self):
        data = self._get_list(
            self._get_authorised_user(),
            prisoner_count__gte=3,
        )['results']
        prisoner_counts = Disbursement.objects.filter(
            method=DisbursementMethod.bank_transfer,
            resolution=DisbursementResolution.sent,
        ).values(
            'sort_code', 'account_number', 'roll_number',
        ).order_by(
            'sort_code', 'account_number', 'roll_number',
        ).annotate(prisoner_count=Count('prisoner_number', distinct=True))

        prisoner_counts = prisoner_counts.filter(prisoner_count__gte=3)

        self.assertEqual(
            len(prisoner_counts), len(data)
        )

    def test_filter_by_prison(self):
        data = self._get_list(self._get_authorised_user(), prison='IXB')['results']

        recipient_profiles = RecipientProfile.objects.filter(
            prisoners__prisons__nomis_id='IXB',
            bank_transfer_details__isnull=False
        ).distinct()

        self.assertEqual(len(data), recipient_profiles.count())
        for recipient in recipient_profiles:
            self.assertTrue(recipient.id in [d['id'] for d in data])

    def test_filter_by_multiple_prisons(self):
        data = self._get_list(self._get_authorised_user(), prison=['IXB', 'INP'])['results']

        recipient_profiles = RecipientProfile.objects.filter(
            Q(prisoners__prisons__nomis_id='IXB') |
            Q(prisoners__prisons__nomis_id='INP'),
            bank_transfer_details__isnull=False
        ).distinct()

        self.assertEqual(len(data), recipient_profiles.count())
        for recipient in recipient_profiles:
            self.assertTrue(recipient.id in [d['id'] for d in data])

    def test_filter_by_monitoring(self):
        user = self._get_authorised_user()

        # the complete set that could be returned
        returned_profiles = RecipientProfile.objects.filter(
            bank_transfer_details__isnull=False
        )

        # make user monitor 2 bank accounts
        profiles = returned_profiles.order_by('?')[:2]
        for profile in profiles:
            profile.bank_transfer_details.first().recipient_bank_account.monitoring_users.add(user)

        expected_recipient_ids = set(returned_profiles.filter(
            bank_transfer_details__recipient_bank_account__monitoring_users=user
        ).values_list('pk', flat=True))

        # can list all unmonitored recipients
        data = self._get_list(user, monitoring=False)['results']
        self.assertEqual(len(data), returned_profiles.count() - 2)
        returned_ids = set(d['id'] for d in data)
        self.assertTrue(returned_ids.isdisjoint(expected_recipient_ids))

        # can list monitored recipients
        data = self._get_list(user, monitoring=True)['results']
        self.assertEqual(len(data), 2)
        returned_ids = set(d['id'] for d in data)
        self.assertSetEqual(returned_ids, expected_recipient_ids)

        # ensure object detail view is accessible
        recipient = profiles.first()
        recipient.bank_transfer_details.first().recipient_bank_account.monitoring_users.add(self.security_staff[1])
        detail_url = reverse('recipientprofile-detail', kwargs={'pk': recipient.pk})
        response = self.client.get(
            detail_url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['id'], recipient.pk)
        self.assertTrue(response.data['monitoring'])


class RecipientProfileDisbursementListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('recipient-disbursements-list', args=args)

    def test_list_disbursements_for_recipient(self):
        recipient = RecipientProfile.objects.last()  # first is anonymous/cheque
        data = self._get_list(
            self._get_authorised_user(), path_params=[recipient.id]
        )['results']
        self.assertGreater(len(data), 0)

        self.assertEqual(
            len(recipient.disbursements.all()), len(data)
        )
        for disbursement in recipient.disbursements.all():
            self.assertTrue(disbursement.id in [d['id'] for d in data])
