from collections import defaultdict
from itertools import chain

from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status as http_status

from credit.models import Credit
from credit.constants import CreditResolution
from payment.constants import PaymentStatus
from payment.tests.utils import generate_payments
from security.constants import CheckStatus
from security.models import Check, PrisonerProfile
from security.tests.test_views import SecurityViewTestCase


class PrisonerProfileListTestCase(SecurityViewTestCase):
    def _get_authorised_user(self):
        return self.test_users['security_fiu_users'][0]

    def _get_url(self, *args, **kwargs):
        return reverse('prisonerprofile-list')

    def test_search_by_simple_search_param(self):
        """
        Test for when the search param `simple_search` is used.

        Checks that the API returns the prisoners with the supplied search value in
            prisoner name
            OR
            prisoner number
        """
        # change the loaded data so that the test matches exactly 2 records
        term_part1 = get_random_string(10)
        term_part2 = get_random_string(10)
        term = f'{term_part1} {term_part2}'

        prisoners = list(PrisonerProfile.objects.all()[:3])

        prisoners[0].prisoner_name = f'{term}Junior'.upper()
        prisoners[0].save()

        prisoners[1].prisoner_name = term_part1
        prisoners[1].prisoner_number = term_part2
        prisoners[1].save()

        # this should not be matched as only term_part1 is present
        prisoners[2].prisoner_name = term_part1
        prisoners[2].save()

        response_data = self._get_list(
            self._get_authorised_user(),
            simple_search=term,
        )['results']

        self.assertEqual(len(response_data), 2)
        self.assertEqual(
            {item['id'] for item in response_data},
            {
                prisoners[0].id,
                prisoners[1].id,
            },
        )

    def test_filter_by_sender_count(self):
        data = self._get_list(self._get_authorised_user(), sender_count__gte=3)['results']
        bank_pairs = (
            Credit.objects.filter(
                transaction__isnull=False,
                prisoner_number__isnull=False,
                sender_profile_id__isnull=False
            ).values(
                'prisoner_number',
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number'
            ).order_by(
                'prisoner_number',
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number'
            ).distinct()
        )

        card_pairs = (
            Credit.objects.filter(
                payment__isnull=False,
                prisoner_number__isnull=False,
                sender_profile_id__isnull=False
            ).values(
                'prisoner_number',
                'payment__card_expiry_date',
                'payment__card_number_last_digits',
                'payment__billing_address__postcode'
            ).order_by(
                'prisoner_number',
                'payment__card_expiry_date',
                'payment__card_number_last_digits',
                'payment__billing_address__postcode'
            ).distinct()
        )

        total_counts = defaultdict(int)
        for pair in chain(bank_pairs, card_pairs):
            total_counts[pair['prisoner_number']] += 1

        greater_than_3_count = 0
        for prisoner in total_counts:
            if total_counts[prisoner] >= 3:
                greater_than_3_count += 1

        self.assertEqual(
            greater_than_3_count, len(data)
        )

    def test_filter_by_current_prison(self):
        """
        Test filtering prisoners by current prison as single value.
        """
        prison_id = 'IXB'
        response = self._get_list(
            self._get_authorised_user(),
            current_prison=prison_id,
        )
        actual_results = response['results']

        actual_prisoner_profiles = PrisonerProfile.objects.filter(
            current_prison__nomis_id=prison_id,
        ).distinct()

        self.assertTrue(actual_results)
        self.assertEqual(
            len(actual_results),
            actual_prisoner_profiles.count(),
        )
        self.assertCountEqual(
            actual_prisoner_profiles.values_list('id', flat=True),
            [profile['id'] for profile in actual_results],
        )

    def test_filter_by_list_of_current_prisons(self):
        """
        Test filtering prisoners by current prison as multi value.
        """
        prison_ids = ['IXB', 'INP']
        response = self._get_list(
            self._get_authorised_user(),
            current_prison=prison_ids,
        )
        actual_results = response['results']

        actual_prisoner_profiles = PrisonerProfile.objects.filter(
            current_prison__nomis_id__in=prison_ids,
        ).distinct()

        self.assertTrue(actual_results)
        self.assertEqual(
            len(actual_results),
            actual_prisoner_profiles.count(),
        )
        self.assertCountEqual(
            actual_prisoner_profiles.values_list('id', flat=True),
            [profile['id'] for profile in actual_results],
        )

    def test_filter_by_monitoring(self):
        user = self._get_authorised_user()

        # the complete set that could be returned
        returned_profiles = PrisonerProfile.objects.all()

        # make user monitor 2 prisoners
        profiles = returned_profiles.order_by('?')[:2]
        for profile in profiles:
            profile.monitoring_users.add(user)

        expected_prisoner_ids = set(returned_profiles.filter(
            monitoring_users=user
        ).values_list('pk', flat=True))

        # can list all unmonitored recipients
        data = self._get_list(user, monitoring=False)['results']
        self.assertEqual(len(data), returned_profiles.count() - 2)
        returned_ids = set(d['id'] for d in data)
        self.assertTrue(returned_ids.isdisjoint(expected_prisoner_ids))

        # can list monitored recipients
        data = self._get_list(user, monitoring=True)['results']
        self.assertEqual(len(data), 2)
        returned_ids = set(d['id'] for d in data)
        self.assertSetEqual(returned_ids, expected_prisoner_ids)

        # ensure object detail view is accessible
        profile = profiles.first()
        profile.monitoring_users.add(self.security_staff[1])
        detail_url = reverse('prisonerprofile-detail', kwargs={'pk': profile.pk})
        response = self.client.get(
            detail_url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['id'], profile.pk)
        self.assertTrue(response.data['monitoring'])


class PrisonerCreditListTestCase(SecurityViewTestCase):
    def _get_authorised_user(self):
        return self.test_users['security_fiu_users'][0]

    def _get_url(self, *args, **kwargs):
        return reverse('prisoner-credits-list', args=args)

    def test_list_credits_for_prisoner(self):
        prisoner = PrisonerProfile.objects.first()
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner.id]
        )['results']
        self.assertTrue(len(data) > 0)

        self.assertEqual(
            len(prisoner.credits.all()), len(data)
        )
        for credit in prisoner.credits.all():
            self.assertTrue(credit.id in [d['id'] for d in data])

        self.assertFalse(
            any(
                d['resolution'] in (CreditResolution.failed.value, CreditResolution.initial.value)
                for d in data
            )
        )

    def test_list_credits_for_prisoner_includes_not_completed(self):
        payments = generate_payments(10, days_of_history=1, overrides={'status': PaymentStatus.rejected.value})
        prisoner_profile_id = list(
            filter(lambda p: p.credit.prisoner_profile_id, payments)
        )[0].credit.prisoner_profile_id
        credits = Credit.objects_all.filter(
            prisoner_profile_id=prisoner_profile_id
        )
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner_profile_id], only_completed=False
        )['results']
        self.assertTrue(len(data) > 0)

        self.assertEqual(
            len(credits), len(data)
        )
        for credit in credits:
            self.assertTrue(credit.id in [d['id'] for d in data])

        self.assertTrue(
            any(
                d['resolution'] in (CreditResolution.failed.value, CreditResolution.initial.value)
                for d in data
            )
        )

    def test_list_credits_for_prisoner_include_checks(self):
        # Setup
        prisoner = PrisonerProfile.objects.order_by('-credit_count').first()
        accepted_checks = []
        rejected_checks = []
        user = self._get_authorised_user()
        for credit in prisoner.credits.all():
            check = Check.objects.create_for_credit(credit)
            if check.status == CheckStatus.pending.value:
                check.reject(user, 'looks dodgy', {'payment_source_linked_other_prisoners': True})
                rejected_checks.append(credit.id)
            elif check.status == CheckStatus.accepted.value:
                accepted_checks.append(credit.id)

        # Execute
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner.id], include_checks=True
        )['results']

        # Assert
        self.assertGreater(len(data), 0)
        self.assertEqual(
            len(prisoner.credits.all()), len(data)
        )
        for credit in prisoner.credits.all():
            self.assertTrue(credit.id in [d['id'] for d in data])

        for datum in data:
            self.assertIn('security_check', datum)
            self.assertIn('rules', datum['security_check'])
            self.assertIn('description', datum['security_check'])
            self.assertIn('actioned_by', datum['security_check'])
            if datum['id'] in accepted_checks:
                self.assertEqual(datum['security_check']['status'], 'accepted')
                self.assertListEqual(
                    datum['security_check']['description'],
                    ['Credit matched no rules and was automatically accepted'],
                )
            if datum['id'] in rejected_checks:
                self.assertEqual(datum['security_check']['status'], 'rejected')
                self.assertEqual(datum['security_check']['decision_reason'], 'looks dodgy')
                self.assertEqual(datum['security_check']['actioned_by'], user.id)
                self.assertEqual(
                    datum['security_check']['rejection_reasons'],
                    {'payment_source_linked_other_prisoners': True}
                )


class PrisonerDisbursementListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('prisoner-disbursements-list', args=args)

    def test_list_disbursements_for_prisoner(self):
        prisoner = PrisonerProfile.objects.order_by('-disbursement_count').first()
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner.id]
        )['results']
        self.assertTrue(len(data) > 0)

        self.assertEqual(
            len(prisoner.disbursements.all()), len(data)
        )
        for disbursement in prisoner.disbursements.all():
            self.assertTrue(disbursement.id in [d['id'] for d in data])
