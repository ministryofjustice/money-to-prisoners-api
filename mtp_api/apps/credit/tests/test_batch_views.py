from django.urls import reverse
from rest_framework import status

from credit.models import ProcessingBatch
from credit.tests.test_base import BaseCreditViewTestCase
from mtp_auth.models import PrisonUserMapping


class CreateProcessingBatchTestCase(BaseCreditViewTestCase):

    def test_create_processing_batch_succeeds(self):
        user = self.prison_clerks[0]
        user_prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
        available_credits = self._get_credit_pending_credits_qs(
            user_prisons, user
        ).values_list('id', flat=True)

        new_processing_batch = {
            'credits': available_credits,
        }

        response = self.client.post(
            reverse('processingbatch-list'), data=new_processing_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        batches = ProcessingBatch.objects.all()
        self.assertEqual(batches.count(), 1)
        self.assertEqual(
            sorted(batches.first().credits.values_list('id', flat=True)),
            sorted(available_credits)
        )
        self.assertFalse(batches.first().expired)
