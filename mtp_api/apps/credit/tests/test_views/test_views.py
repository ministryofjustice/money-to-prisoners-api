import datetime

from django.urls import reverse
from django.utils.dateparse import parse_date
from rest_framework import status

from credit.models import Credit, Log
from credit.constants import CREDIT_RESOLUTION, LogAction
from credit.tests.test_base import BaseCreditViewTestCase
from credit.tests.test_views.test_credit_list import CashbookCreditRejectsRequestsWithoutPermissionTestMixin
from mtp_auth.models import PrisonUserMapping


class CreditCreditsTestCase(
    CashbookCreditRejectsRequestsWithoutPermissionTestMixin,
    BaseCreditViewTestCase
):
    ENDPOINT_VERB = 'post'

    def _get_url(self, **filters):
        return reverse('credit-credit')

    def test_credit_credits(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        available_qs = self._get_credit_pending_credits_qs(managing_prisons, logged_in_user)
        credited_qs = self._get_credited_credits_qs(managing_prisons, logged_in_user)

        self.assertTrue(available_qs.count() > 0)

        to_credit = list(available_qs.values_list('id', flat=True))

        data = [
            {'id': c_id, 'credited': True, 'nomis_transaction_id': 'nomis%s' % c_id}
            for c_id in to_credit
        ]
        response = self.client.post(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check db
        self.assertEqual(
            credited_qs.filter(id__in=to_credit).count(), len(to_credit)
        )
        for credit in credited_qs.filter(id__in=to_credit):
            self.assertEqual(credit.nomis_transaction_id, 'nomis%s' % credit.id)
        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=logged_in_user,
                action=LogAction.credited,
                credit__id__in=to_credit
            ).count(),
            len(to_credit)
        )

    def test_missing_ids(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.post(
            self._get_url(), data=[],
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_invalid_format(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.post(
            self._get_url(), data=[{}],
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SetManualCreditsTestCase(
    CashbookCreditRejectsRequestsWithoutPermissionTestMixin,
    BaseCreditViewTestCase
):
    ENDPOINT_VERB = 'post'

    def _get_url(self, **filters):
        return reverse('setmanual-credit')

    def test_set_manual_credits(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        available_qs = self._get_credit_pending_credits_qs(managing_prisons, logged_in_user)
        manual_qs = self._get_queryset(logged_in_user, managing_prisons).filter(
            owner=logged_in_user,
            resolution=CREDIT_RESOLUTION.MANUAL,
            prison__in=managing_prisons
        )

        self.assertTrue(available_qs.count() > 0)

        to_set_manual = list(available_qs.values_list('id', flat=True))

        data = {
            'credit_ids': to_set_manual
        }
        response = self.client.post(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check db
        self.assertEqual(
            manual_qs.filter(id__in=to_set_manual).count(), len(to_set_manual)
        )
        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=logged_in_user,
                action=LogAction.manual,
                credit__id__in=to_set_manual,
            ).count(),
            len(to_set_manual)
        )

    def test_missing_ids(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.post(
            self._get_url(), data={
                'credit_ids': []
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_invalid_format(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.post(
            self._get_url(), data={},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewCreditTestCase(
    CashbookCreditRejectsRequestsWithoutPermissionTestMixin,
    BaseCreditViewTestCase
):
    ENDPOINT_VERB = 'post'

    def _get_authorised_user(self):
        return self.security_staff[0]

    def _get_url(self):
        return reverse('credit-review')

    def test_can_mark_credits_reviewed(self):
        logged_in_user = self._get_authorised_user()
        reviewed = Credit.objects.credit_pending()[:10].values_list('id', flat=True)

        response = self.client.post(
            self._get_url(),
            {'credit_ids': reviewed},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertEqual(
            set(reviewed),
            set(Credit.objects.filter(reviewed=True).values_list('id', flat=True))
        )

        reviewed_logs = Log.objects.filter(
            user=logged_in_user,
            action=LogAction.reviewed,
        )
        self.assertEqual(len(reviewed_logs), len(reviewed))
        for log in reviewed_logs:
            self.assertTrue(log.credit.id in reviewed)


class CreditsGroupedByCreditedListTestCase(
    CashbookCreditRejectsRequestsWithoutPermissionTestMixin,
    BaseCreditViewTestCase
):
    ENDPOINT_VERB = 'get'

    def _get_authorised_user(self):
        return self.prison_clerks[0]

    def _get_url(self):
        return reverse('credit-processed-list')

    def _get_credits_grouped_by_credited_list(self, filters):
        logged_in_user = self._get_authorised_user()

        response = self.client.get(
            self._get_url(),
            filters,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        return response

    def test_credits_grouped_by_credited_list(self):
        response = self._get_credits_grouped_by_credited_list({})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        credits = [
            c for c in self._get_managed_prison_credits()
            if c.resolution == CREDIT_RESOLUTION.CREDITED
        ]
        for group in response.data['results']:
            total = 0
            count = 0
            for credit in credits:
                for log in Log.objects.filter(credit=credit):
                    if (log.action == LogAction.credited.value and
                            log.created.date() == parse_date(group['logged_at']) and
                            log.user.id == group['owner']):
                        total += credit.amount
                        count += 1
                        break
            self.assertEqual(count, group['count'])
            self.assertEqual(total, group['total'])

    def test_credits_grouped_by_credited_list_filtered_by_date(self):
        start_date = datetime.date.today() - datetime.timedelta(days=2)
        end_date = datetime.date.today() - datetime.timedelta(days=1)
        response = self._get_credits_grouped_by_credited_list({
            'logged_at__gte': start_date.isoformat(),
            'logged_at__lt': end_date.isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for group in response.data['results']:
            self.assertGreaterEqual(
                parse_date(group['logged_at']),
                start_date
            )
            self.assertLess(
                parse_date(group['logged_at']),
                end_date
            )
