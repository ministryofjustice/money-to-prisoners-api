import datetime
import random

from django.core.management import call_command
from django.urls import reverse
from django.utils.dateparse import parse_date
from rest_framework import status

from core import getattr_path
from credit.models import Credit, Log
from credit.constants import (
    LOG_ACTIONS, CREDIT_RESOLUTION
)
from credit.tests.test_base import (
    BaseCreditViewTestCase
)
from credit.tests.test_views.test_credit_list import (
    CreditListTestCase, CashbookCreditRejectsRequestsWithoutPermissionTestMixin
)
from mtp_auth.models import PrisonUserMapping
from security.models import (
    BankAccount, DebitCardSenderDetails, PrisonerProfile
)


class SecurityCreditListTestCase(CreditListTestCase):
    def _get_authorised_user(self):
        return self.security_staff[0]

    def _test_response_with_filters(self, filters):
        response = super()._test_response_with_filters(filters)
        for response_credit in response.data['results']:
            db_credit = Credit.objects.get(pk=response_credit['id'])
            self.assertEqual(
                db_credit.sender_sort_code,
                response_credit.get('sender_sort_code')
            )
            self.assertEqual(
                db_credit.sender_account_number,
                response_credit.get('sender_account_number')
            )
            self.assertEqual(
                db_credit.sender_roll_number,
                response_credit.get('sender_roll_number')
            )


class TransactionSenderDetailsCreditListTestCase(SecurityCreditListTestCase):
    def test_sort_code_filter(self):
        random_sort_code = (
            Credit.objects.filter(transaction__sender_sort_code__isnull=False)
            .exclude(transaction__sender_sort_code='')
            .order_by('?').first().sender_sort_code
        )
        self._test_response_with_filters({
            'sender_sort_code': random_sort_code
        })

    def test_account_number_filter(self):
        random_account_number = (
            Credit.objects.filter(transaction__sender_account_number__isnull=False)
            .exclude(transaction__sender_account_number='')
            .order_by('?').first().sender_account_number
        )
        self._test_response_with_filters({
            'sender_account_number': random_account_number
        })

    def test_roll_number_filter(self):
        random_roll_number = (
            Credit.objects.filter(transaction__sender_roll_number__isnull=False)
            .exclude(transaction__sender_roll_number='')
            .order_by('?').first().sender_roll_number
        )
        self._test_response_with_filters({
            'sender_roll_number': random_roll_number
        })


class CreditListWithBlankStringFiltersTestCase(SecurityCreditListTestCase):
    def assertAllResponsesHaveBlankField(self, filters, blank_fields, expected_filter):  # noqa: N802
        expected_results = list(filter(expected_filter, self._get_managed_prison_credits()))

        url = self._get_url(**filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self._get_authorised_user())
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = []
        for result in response.data.get('results', []):
            results.append(result['id'])
            for blank_field in blank_fields:
                self.assertIn(result[blank_field], ['', None])

        self.assertListEqual(
            sorted(results),
            sorted(expected_result.id for expected_result in expected_results)
        )

    def test_blank_sender_name(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_name__isblank': 'True'
            },
            ['sender_name'],
            lambda credit: getattr_path(credit, 'transaction.sender_name', None) == ''
        )

    def test_blank_sender_sort_code(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_sort_code__isblank': 'True'
            },
            ['sender_sort_code'],
            lambda credit: getattr_path(credit, 'transaction.sender_sort_code', None) == ''
        )

    def test_blank_sender_account_number(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_account_number__isblank': 'True'
            },
            ['sender_account_number'],
            lambda credit: getattr_path(credit, 'transaction.sender_account_number', None) == ''
        )

    def test_blank_sender_roll_number(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_roll_number__isblank': 'True'
            },
            ['sender_roll_number'],
            lambda credit: getattr_path(credit, 'transaction.sender_roll_number', None) == ''
        )


class PrisonerNumberCreditListTestCase(SecurityCreditListTestCase):
    def test_prisoner_number_filter(self):
        random_prisoner_number = (
            Credit.objects.filter(prisoner_number__isnull=False)
            .exclude(prisoner_number='')
            .order_by('?').first().prisoner_number
        )
        self._test_response_with_filters({
            'prisoner_number': random_prisoner_number
        })


class AmountPatternCreditListTestCase(SecurityCreditListTestCase):
    def test_exclude_amount_pattern_filter_endswith_multiple(self):
        self._test_response_with_filters({
            'exclude_amount__endswith': ['000', '500'],
        })

    def test_exclude_amount_pattern_filter_regex(self):
        self._test_response_with_filters({
            'exclude_amount__regex': '^.*000$',
        })

    def test_amount_pattern_filter_endswith(self):
        self._test_response_with_filters({
            'amount__endswith': '000',
        })

    def test_amount_pattern_filter_endswith_multiple(self):
        self._test_response_with_filters({
            'amount__endswith': ['000', '500'],
        })

    def test_amount_pattern_filter_regex(self):
        self._test_response_with_filters({
            'amount__regex': '^.*000$',
        })

    def test_amount_pattern_filter_less_than_regex(self):
        self._test_response_with_filters({
            'amount__lte': 5000,
            'amount__regex': '^.*00$',
        })

    def test_amount_pattern_filter_range(self):
        self._test_response_with_filters({
            'amount__gte': 5000,
            'amount__lte': 10000,
        })

    def test_amount_pattern_filter_exact(self):
        random_amount = random.choice(self.credits).amount
        self._test_response_with_filters({
            'amount': random_amount,
        })


class NoPrisonCreditListTestCase(SecurityCreditListTestCase):
    def test_no_prison_filter(self):
        self._test_response_with_filters({
            'prison__isnull': 'True'
        })


class MonitoredCreditListTestCase(SecurityCreditListTestCase):
    def test_list_credits_of_monitored_prisoner(self):
        call_command('update_security_profiles')
        user = self._get_authorised_user()
        prisoner_profile = PrisonerProfile.objects.first()
        prisoner_profile.monitoring_users.add(user)

        response = self._test_response({'monitored': True})

        self.assertEqual(
            sorted(c['id'] for c in response.data['results']),
            sorted(prisoner_profile.credits.values_list('id', flat=True))
        )

    def test_list_credits_of_monitored_bank_account(self):
        call_command('update_security_profiles')
        user = self._get_authorised_user()
        bank_account = BankAccount.objects.first()
        bank_account.monitoring_users.add(user)

        response = self._test_response({'monitored': True})

        self.assertEqual(
            sorted(c['id'] for c in response.data['results']),
            sorted(
                bank_account.senders.first().sender.credits.values_list(
                    'id', flat=True
                )
            )
        )

    def test_list_credits_of_monitored_debit_card(self):
        call_command('update_security_profiles')
        user = self._get_authorised_user()
        debit_card = DebitCardSenderDetails.objects.first()
        debit_card.monitoring_users.add(user)

        response = self._test_response({'monitored': True})

        self.assertEqual(
            sorted(c['id'] for c in response.data['results']),
            sorted(
                debit_card.sender.credits.values_list(
                    'id', flat=True
                )
            )
        )

    def test_list_credits_of_monitored_debit_card_and_prisoner(self):
        call_command('update_security_profiles')
        user = self._get_authorised_user()
        debit_card = DebitCardSenderDetails.objects.first()
        debit_card.monitoring_users.add(user)
        prisoner_profile = PrisonerProfile.objects.first()
        prisoner_profile.monitoring_users.add(user)

        response = self._test_response({'monitored': True})

        self.assertEqual(
            sorted(c['id'] for c in response.data['results']),
            sorted(
                prisoner_profile.credits.all().union(
                    debit_card.sender.credits.all()
                ).values_list(
                    'id', flat=True
                )
            )
        )

    def test_list_ordered_monitored_credits(self):
        call_command('update_security_profiles')
        user = self._get_authorised_user()
        debit_card = DebitCardSenderDetails.objects.first()
        debit_card.monitoring_users.add(user)
        prisoner_profile = PrisonerProfile.objects.first()
        prisoner_profile.monitoring_users.add(user)

        response = self._test_response({'monitored': True, 'ordering': 'received_at'})

        self.assertEqual(
            [c['id'] for c in response.data['results']],
            [c.id for c in prisoner_profile.credits.all().union(
                debit_card.sender.credits.all()
            ).order_by('received_at', 'id')]
        )


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
                action=LOG_ACTIONS.CREDITED,
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
                action=LOG_ACTIONS.MANUAL,
                credit__id__in=to_set_manual
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
            action=LOG_ACTIONS.REVIEWED,
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
                    if (log.action == LOG_ACTIONS.CREDITED and
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
