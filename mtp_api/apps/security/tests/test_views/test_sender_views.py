from django.db.models import Count, Q
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status as http_status

from credit.models import Credit
from credit.constants import CreditResolution
from payment.constants import PaymentStatus
from payment.tests.utils import generate_payments
from security.constants import CheckStatus
from security.models import Check, SenderProfile
from security.tests.test_views import SecurityViewTestCase


class SenderProfileListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('senderprofile-list')

    def test_search_by_simple_search_param(self):
        """
        Test for when the search param `simple_search` is used.

        Checks that the API returns the senders with the supplied search value in
            the sender name of a transfer bank details object
            OR
            the cardholder name of a debit card details object
            OR
            the sender email of a debit card details object
        """
        # change the loaded data so that the test matches exactly 3 records
        term_part1 = get_random_string(10)
        term_part2 = get_random_string(10)
        term = f'{term_part1} {term_part2}'

        profiles_qs = SenderProfile.objects.annotate(
            bank_transfer_count=Count('bank_transfer_details'),
            debit_card_count=Count('debit_card_details'),
        ).order_by('?')

        bank_transfer_sender = profiles_qs.filter(
            bank_transfer_count__gt=0,
            debit_card_count=0,
        ).first()
        bank_transfer_details = bank_transfer_sender.bank_transfer_details.first()
        bank_transfer_details.sender_name = f'{term}Junior'.upper()
        bank_transfer_details.save()

        debit_card_senders = list(
            profiles_qs.filter(
                bank_transfer_count=0,
                debit_card_count__gt=0,
            ).distinct()[:3]
        )

        debit_card_sender = debit_card_senders[0]
        debit_card_details = debit_card_sender.debit_card_details.first()
        cardholder = debit_card_details.cardholder_names.first()
        cardholder.name = f'Mr{term_part1}an {term_part2}'
        cardholder.save()

        debit_card_sender = debit_card_senders[1]
        debit_card_details = debit_card_sender.debit_card_details.first()
        cardholder = debit_card_details.cardholder_names.first()
        sender_email = debit_card_details.sender_emails.first()
        cardholder.name = term_part1
        cardholder.save()
        sender_email.email = f'{term_part2}@example.com'
        sender_email.save()

        # this should not be matched as only term_part1 is present
        debit_card_sender = debit_card_senders[2]
        debit_card_details = debit_card_sender.debit_card_details.first()
        cardholder = debit_card_details.cardholder_names.first()
        cardholder.name = f'Mr{term_part1}'
        cardholder.save()

        response_data = self._get_list(
            self._get_authorised_user(),
            simple_search=term,
        )['results']

        self.assertEqual(len(response_data), 3)
        self.assertEqual(
            {item['id'] for item in response_data},
            {
                bank_transfer_sender.id,
                debit_card_senders[0].id,
                debit_card_senders[1].id,
            },
        )

    def test_filter_by_prisoner_count(self):
        data = self._get_list(self._get_authorised_user(), prisoner_count__gte=3)['results']
        bank_prisoner_counts = Credit.objects.filter(
            transaction__isnull=False,
            prisoner_profile_id__isnull=False,
        ).values(
            'transaction__sender_name',
            'transaction__sender_sort_code',
            'transaction__sender_account_number',
            'transaction__sender_roll_number',
        ).order_by(
            'transaction__sender_name',
            'transaction__sender_sort_code',
            'transaction__sender_account_number',
            'transaction__sender_roll_number'
        ).annotate(prisoner_count=Count('prisoner_number', distinct=True))

        bank_prisoner_counts = bank_prisoner_counts.filter(prisoner_count__gte=3)

        card_prisoner_counts = Credit.objects.filter(
            payment__isnull=False,
            prisoner_profile_id__isnull=False,
        ).values(
            'payment__card_expiry_date',
            'payment__card_number_last_digits',
            'payment__billing_address__postcode',
        ).order_by(
            'payment__card_expiry_date',
            'payment__card_number_last_digits',
            'payment__billing_address__postcode'
        ).annotate(prisoner_count=Count('prisoner_number', distinct=True))
        card_prisoner_counts = card_prisoner_counts.filter(prisoner_count__gte=3)

        self.assertEqual(
            len(bank_prisoner_counts) + len(card_prisoner_counts), len(data)
        )

    def test_filter_by_prison(self):
        data = self._get_list(self._get_authorised_user(), prison='IXB')['results']

        sender_profiles = SenderProfile.objects.filter(
            prisoners__prisons__nomis_id='IXB'
        ).distinct()

        self.assertEqual(len(data), sender_profiles.count())
        for sender in sender_profiles:
            self.assertTrue(sender.id in [d['id'] for d in data])

    def test_filter_by_multiple_prisons(self):
        data = self._get_list(self._get_authorised_user(), prison=['IXB', 'INP'])['results']

        sender_profiles = SenderProfile.objects.filter(
            Q(prisoners__prisons__nomis_id='IXB') |
            Q(prisoners__prisons__nomis_id='INP')
        ).distinct()

        self.assertEqual(len(data), sender_profiles.count())
        for sender in sender_profiles:
            self.assertTrue(sender.id in [d['id'] for d in data])

    def test_filter_by_monitoring(self):
        user = self._get_authorised_user()

        # the complete set that could be returned
        returned_profiles = SenderProfile.objects.all()

        # make user monitor 2 debit cards and 2 bank accounts
        bank_transfer_profiles = returned_profiles.filter(
            bank_transfer_details__isnull=False
        ).order_by('?')[:2]
        for profile in bank_transfer_profiles:
            profile.bank_transfer_details.first().sender_bank_account.monitoring_users.add(user)
        debit_card_profiles = returned_profiles.filter(
            debit_card_details__isnull=False
        ).order_by('?')[:2]
        for profile in debit_card_profiles:
            profile.debit_card_details.first().monitoring_users.add(user)

        expected_bank_transfer_ids = set(returned_profiles.filter(
            bank_transfer_details__sender_bank_account__monitoring_users=user
        ).values_list('pk', flat=True))
        expected_debit_card_ids = set(returned_profiles.filter(
            debit_card_details__monitoring_users=user
        ).values_list('pk', flat=True))
        expected_sender_ids = expected_bank_transfer_ids | expected_debit_card_ids

        # can list all unmonitored senders
        data = self._get_list(user, monitoring=False)['results']
        self.assertEqual(len(data), returned_profiles.count() - 4)
        returned_ids = set(d['id'] for d in data)
        self.assertTrue(returned_ids.isdisjoint(expected_sender_ids))

        # can list monitored senders
        data = self._get_list(user, monitoring=True)['results']
        self.assertEqual(len(data), 4)
        returned_ids = set(d['id'] for d in data)
        self.assertSetEqual(returned_ids, expected_sender_ids)

        # ensure object detail view is accessible
        profile = debit_card_profiles.first()
        profile.debit_card_details.first().monitoring_users.add(self.security_staff[1])
        detail_url = reverse('senderprofile-detail', kwargs={'pk': profile.pk})
        response = self.client.get(
            detail_url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['id'], profile.pk)
        self.assertTrue(response.data['monitoring'])


class SenderCreditListTestCase(SecurityViewTestCase):
    def _get_authorised_user(self):
        return self.test_users['security_fiu_users'][0]

    def _get_url(self, *args, **kwargs):
        return reverse('sender-credits-list', args=args)

    def test_list_credits_for_sender(self):
        sender = SenderProfile.objects.last()  # first is anonymous
        data = self._get_list(
            self._get_authorised_user(), path_params=[sender.id]
        )['results']
        self.assertGreater(len(data), 0)

        self.assertEqual(
            len(sender.credits.all()), len(data)
        )
        for credit in sender.credits.all():
            self.assertTrue(credit.id in [d['id'] for d in data])

        self.assertFalse(
            any(
                d['resolution'] in (CreditResolution.failed.value, CreditResolution.initial.value)
                for d in data
            )
        )

    def test_list_credits_for_sender_includes_not_completed(self):
        payments = generate_payments(10, days_of_history=1, overrides={'status': PaymentStatus.rejected.value})
        sender_profile_id = list(filter(lambda p: p.credit.sender_profile_id, payments))[0].credit.sender_profile_id
        credits = Credit.objects_all.filter(
            sender_profile_id=sender_profile_id
        )
        data = self._get_list(
            self._get_authorised_user(), path_params=[sender_profile_id], only_completed=False
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

    def test_list_credits_for_sender_include_checks(self):
        # Setup
        sender = SenderProfile.objects.order_by('-credit_count').first()
        accepted_checks = []
        rejected_checks = []
        user = self._get_authorised_user()
        for credit in sender.credits.all():
            check = Check.objects.create_for_credit(credit)
            if check.status == CheckStatus.pending.value:
                check.reject(user, 'looks dodgy', {'payment_source_linked_other_prisoners': True})
                rejected_checks.append(credit.id)
            elif check.status == CheckStatus.accepted.value:
                accepted_checks.append(credit.id)

        # Execute
        data = self._get_list(
            self._get_authorised_user(), path_params=[sender.id], include_credits=True
        )['results']

        # Assert
        self.assertGreater(len(data), 0)
        self.assertEqual(
            len(sender.credits.all()), len(data)
        )
        for credit in sender.credits.all():
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
