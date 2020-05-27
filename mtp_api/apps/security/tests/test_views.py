import datetime
from collections import defaultdict
from itertools import chain
from unittest import mock

from django.core.management import call_command
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.timezone import make_aware, now
from model_mommy import mommy
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import format_date_or_datetime, make_test_users
from credit.models import Credit
from credit.constants import CREDIT_RESOLUTION
from disbursement.constants import DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from mtp_auth.tests.utils import AuthTestCaseMixin
from mtp_auth.tests.mommy_recipes import create_security_staff_user
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import CHECK_STATUS
from security.models import (
    Check,
    PrisonerProfile,
    RecipientProfile,
    SavedSearch,
    SearchFilter,
    SenderProfile,
)
from transaction.tests.utils import generate_transactions


class SecurityViewTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.test_users = make_test_users()
        self.prison_clerks = self.test_users['prison_clerks']
        self.security_staff = self.test_users['security_staff']
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=150, days_of_history=5)
        call_command('update_security_profiles')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_url(self, *args, **kwargs):
        raise NotImplementedError

    def _get_authorised_user(self):
        return self.security_staff[0]

    def _get_list(self, user, path_params=(), **filters):
        url = self._get_url(*path_params)

        if 'limit' not in filters:
            filters['limit'] = 1000
        response = self.client.get(
            url, filters, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        return response.data


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
        bank_prisoner_counts = Credit.objects.filter(transaction__isnull=False).values(
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

        card_prisoner_counts = Credit.objects.filter(payment__isnull=False).values(
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

    def test_list_credits_for_sender_include_checks(self):
        # Setup
        sender = SenderProfile.objects.last()  # first is anonymous
        accepted_checks = []
        rejected_checks = []
        user = self._get_authorised_user()
        for credit in sender.credits.all():
            check = Check.objects.create_for_credit(credit)
            if check.status != 'accepted':
                check.reject(user, 'looks dodgy')
                rejected_checks.append(credit.id)

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
                self.assertEqual(
                    datum['security_check']['description'],
                    'Credit matched no rules and was automatically accepted'
                )
                self.assertEqual(datum['security_check']['user'], user.id)
            if datum['id'] in accepted_checks:
                self.assertEqual(datum['security_check']['status'], 'rejected')
                self.assertEqual(datum['security_check']['description'], 'looks dodgy')
                self.assertEqual(datum['security_check']['user'], user.id)


class RecipientProfileListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('recipientprofile-list')

    def test_filter_by_prisoner_count(self):
        data = self._get_list(
            self._get_authorised_user(),
            prisoner_count__gte=3,
        )['results']
        prisoner_counts = Disbursement.objects.filter(
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            resolution=DISBURSEMENT_RESOLUTION.SENT
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
            Credit.objects.filter(transaction__isnull=False, prisoner_number__isnull=False).values(
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
            Credit.objects.filter(payment__isnull=False, prisoner_number__isnull=False).values(
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

    def test_list_credits_for_prisoner_include_checks(self):
        # Setup
        prisoner = PrisonerProfile.objects.first()
        accepted_checks = []
        rejected_checks = []
        user = self._get_authorised_user()
        for credit in prisoner.credits.all():
            check = Check.objects.create_for_credit(credit)
            if check.status != 'accepted':
                check.reject(user, 'looks dodgy')
                rejected_checks.append(credit.id)

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
                self.assertEqual(
                    datum['security_check']['description'],
                    'Credit matched no rules and was automatically accepted'
                )
                self.assertEqual(datum['security_check']['user'], user.id)
            if datum['id'] in accepted_checks:
                self.assertEqual(datum['security_check']['status'], 'rejected')
                self.assertEqual(datum['security_check']['description'], 'looks dodgy')
                self.assertEqual(datum['security_check']['user'], user.id)


class PrisonerDisbursementListTestCase(SecurityViewTestCase):
    def _get_url(self, *args, **kwargs):
        return reverse('prisoner-disbursements-list', args=args)

    def test_list_disbursements_for_prisoner(self):
        prisoner = PrisonerProfile.objects.first()
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner.id]
        )['results']
        self.assertTrue(len(data) > 0)

        self.assertEqual(
            len(prisoner.disbursements.all()), len(data)
        )
        for disbursement in prisoner.disbursements.all():
            self.assertTrue(disbursement.id in [d['id'] for d in data])


class CreateSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-list')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_create_saved_search(self):
        url = self._get_url()
        user = self._get_authorised_user()

        data = {
            'description': 'Saved search',
            'endpoint': '/credits',
            'filters': [{'field': 'sender_name', 'value': 'Simon'}]
        }

        response = self.client.post(
            url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        new_search = SavedSearch.objects.all().first()
        self.assertEqual(len(new_search.filters.all()), 1)
        self.assertEqual(new_search.user, user)


class UpdateSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-detail', args=args)

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_update_saved_search(self):
        user = self._get_authorised_user()
        saved_search = SavedSearch.objects.create(
            user=user, description='Saved search', endpoint='/credits')
        SearchFilter.objects.create(
            saved_search=saved_search, field='sender_name', value='Simon'
        )

        url = self._get_url(saved_search.id)

        update = {
            'last_result_count': 12,
            'filters': [{'field': 'sender_name', 'value': 'Thomas'}]
        }

        response = self.client.patch(
            url, data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        self.assertEqual(SavedSearch.objects.all().count(), 1)
        updated_search = SavedSearch.objects.all().first()
        self.assertEqual(updated_search.last_result_count, 12)
        self.assertEqual(len(updated_search.filters.all()), 1)
        self.assertEqual(updated_search.filters.all().first().value, 'Thomas')


class ListSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-list')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_users_can_only_access_their_own_searches(self):
        url = self._get_url()
        user1 = self._get_authorised_user()
        user2 = create_security_staff_user(name_and_password='security-staff-2')

        saved_search_user1 = SavedSearch.objects.create(
            user=user1, description='Saved search for user1', endpoint='/credits')

        saved_search_user2 = SavedSearch.objects.create(
            user=user2, description='Saved search for user2', endpoint='/credits')

        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user1)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['description'], saved_search_user1.description
        )

        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user2)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['description'], saved_search_user2.description
        )


class DeleteSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-detail', args=args)

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_delete_saved_search(self):
        user = self._get_authorised_user()
        saved_search = SavedSearch.objects.create(
            user=user, description='Saved search', endpoint='/credits')
        SearchFilter.objects.create(
            saved_search=saved_search, field='sender_name', value='Simon'
        )

        url = self._get_url(saved_search.id)
        response = self.client.delete(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        self.assertEqual(SavedSearch.objects.all().count(), 0)

    def test_users_can_only_delete_their_own_searches(self):
        user1 = self._get_authorised_user()
        user2 = create_security_staff_user(name_and_password='security-staff-2')

        saved_search_user1 = SavedSearch.objects.create(
            user=user1, description='Saved search for user1')

        url = self._get_url(saved_search_user1.id)
        response = self.client.delete(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user2)
        )
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)


class BaseCheckTestCase(APITestCase, AuthTestCaseMixin):
    """
    Base TestCase for security check endpoints.
    """
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_fiu_users = test_users['security_fiu_users']
        load_random_prisoner_locations()
        generate_payments(payment_batch=100, days_of_history=5)
        self.generate_checks()

    def generate_checks(self):
        # create a pending check for each credit in initial state
        for credit in Credit.objects_all.filter(resolution=CREDIT_RESOLUTION.INITIAL):
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.PENDING,
                rules=['ABC', 'DEF'],
                description='Failed rules',
            )

        for credit in Credit.objects_all.filter(resolution=CREDIT_RESOLUTION.FAILED):
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.REJECTED,
                rules=['ABC', 'DEF'],
                description='Failed rules',
                actioned_at=now(),
                actioned_by=self.security_fiu_users[0],
                decision_reason='because...',
            )

        for credit in Credit.objects.all():
            mommy.make(
                Check,
                credit=credit,
                status=CHECK_STATUS.ACCEPTED,
                rules=['ABC', 'DEF'],
                description='Failed rules',
                actioned_at=now(),
                actioned_by=self.security_fiu_users[0],
            )

    def _get_unauthorised_application_user(self):
        return self.prison_clerks[0]

    def _get_authorised_user(self):
        return self.security_fiu_users[0]

    def assertCheckEqual(self, expected_check, actual_check_data):  # noqa: N802
        expected_data_item = {
            'id': expected_check.pk,
            'description': expected_check.description,
            'rules': expected_check.rules,
            'status': expected_check.status,
            'credit': {
                'id': expected_check.credit.id,
                'amount': expected_check.credit.amount,
                'anonymous': actual_check_data['credit']['anonymous'],
                'billing_address': {
                    'id': expected_check.credit.billing_address.pk,
                    'city': expected_check.credit.billing_address.city,
                    'country': expected_check.credit.billing_address.country,
                    'debit_card_sender_details': expected_check.credit.billing_address.debit_card_sender_details,
                    'line1': expected_check.credit.billing_address.line1,
                    'line2': expected_check.credit.billing_address.line2,
                    'postcode': expected_check.credit.billing_address.postcode,
                } if expected_check.credit.billing_address else None,
                'card_expiry_date': expected_check.credit.card_expiry_date,
                'card_number_first_digits': expected_check.credit.card_number_first_digits,
                'card_number_last_digits': expected_check.credit.card_number_last_digits,
                'comments': [],
                'credited_at': format_date_or_datetime(expected_check.credit.credited_at),
                'intended_recipient': expected_check.credit.intended_recipient,
                'ip_address': expected_check.credit.ip_address,
                'nomis_transaction_id': expected_check.credit.nomis_transaction_id,
                'owner': expected_check.credit.owner.pk if expected_check.credit.owner else None,
                'owner_name': expected_check.credit.owner_name,
                'prison': expected_check.credit.prison.nomis_id,
                'prison_name': expected_check.credit.prison.name,
                'prisoner_name': expected_check.credit.prisoner_name,
                'prisoner_number': expected_check.credit.prisoner_number,
                'prisoner_profile': None,
                'received_at': format_date_or_datetime(expected_check.credit.received_at),
                'reconciliation_code': expected_check.credit.reconciliation_code,
                'refunded_at': None,
                'resolution': expected_check.credit.resolution,
                'reviewed': False,
                'sender_account_number': None,
                'sender_email': expected_check.credit.sender_email,
                'sender_name': expected_check.credit.sender_name,
                'sender_profile': None,
                'sender_roll_number': None,
                'sender_sort_code': None,
                'set_manual_at': None,
                'short_payment_ref': actual_check_data['credit']['short_payment_ref'],
                'source': expected_check.credit.source,
                'started_at': format_date_or_datetime(expected_check.credit.payment.created),
            },
            'actioned_at': format_date_or_datetime(expected_check.actioned_at),
            'actioned_by': expected_check.actioned_by.pk if expected_check.actioned_by else None,
            'actioned_by_name': actual_check_data['actioned_by_name'],
            'decision_reason': expected_check.decision_reason if expected_check.decision_reason else '',
        }
        self.assertDictEqual(actual_check_data, expected_data_item)


class CheckListTestCase(BaseCheckTestCase):
    """
    Tests related to getting security checks.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.get(
            reverse('security-check-list'),
            {},
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_get_all_checks(self):
        """
        Test that the list endpoint returns all checks paginated if no filter is passed in.
        """
        filters = {}

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['count'], Credit.objects_all.count())

        actual_data_item = response_data['results'][0]
        check = Check.objects.get(pk=actual_data_item['id'])

        self.assertCheckEqual(check, actual_data_item)

    def test_get_checks_in_pending(self):
        """
        Test that the list endpoint only returns the checks in pending if a filter is passed in.
        """
        filters = {
            'status': CHECK_STATUS.PENDING,
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            Check.objects.filter(status=CHECK_STATUS.PENDING).count(),
        )
        for item in response_data['results']:
            self.assertEqual(item['status'], CHECK_STATUS.PENDING)

    def test_get_checks_for_specific_rule(self):
        """
        Test that the list endpoint only returns the checks in pending if a filter is passed in.
        """
        filters = {
            'rules': 'ABC',
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            Check.objects.all().count(),
        )
        for item in response_data['results']:
            self.assertIn('ABC', item['rules'])

        filters = {
            'rules': 'XYZ',
        }

        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(
            response_data['count'],
            0,
        )

    def test_check_filtering_by_started_at(self):
        """
        Test that the list endpoint can filter by payment creation date.
        """
        credits_started_at = list(Check.objects.all().order_by('credit__payment__created').values_list(
            'credit__payment__created', flat=True
        ))
        check_count = len(credits_started_at)
        earliest_check = credits_started_at[0].isoformat()
        latest_check = credits_started_at[-1].isoformat()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())

        def assertCheckCount(filters, expected_count):  # noqa: N802
            response = self.client.get(
                reverse('security-check-list'),
                filters,
                format='json',
                HTTP_AUTHORIZATION=auth,
            )
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)
            response_data = response.json()
            self.assertEqual(
                response_data['count'],
                expected_count,
            )

        assertCheckCount(
            {
                'started_at__lt': earliest_check,
            },
            0
        )
        assertCheckCount(
            {
                'started_at__gte': earliest_check,
            },
            check_count
        )
        assertCheckCount(
            {
                'started_at__lt': latest_check,
            },
            check_count - 1
        )

    def test_check_filtering_by_credit_resolution(self):
        """
        Test that the list endpoint can filter by credit resolution.
        """
        # change one check.credit to test that it shouldn't get included in the response
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()
        check.credit.resolution = CREDIT_RESOLUTION.FAILED
        check.credit.save()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            {
                'credit_resolution': CREDIT_RESOLUTION.INITIAL,
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            response.json()['count'],
            Check.objects.filter(status=CHECK_STATUS.PENDING).count() - 1,
        )

    def test_check_filtering_by_actioned_by(self):
        """
        Test that the list endpoint only returns the checks with an actioned_by id.
        """
        filters = {
            'actioned_by': True,
        }

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse('security-check-list'),
            filters,
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        response_data = response.json()

        self.assertEqual(
            response_data['count'],
            Check.objects.filter(actioned_by__isnull=False).count(),
        )

        for item in response_data['results']:
            self.assertIsNotNone(item['actioned_by'])


class GetCheckTestCase(BaseCheckTestCase):
    """
    Tests related to getting a single security check.
    """

    def test_get(self):
        """
        Test that the get object endpoint returns check details.
        """
        check = Check.objects.first()

        auth = self.get_http_authorization_for_user(self._get_authorised_user())
        response = self.client.get(
            reverse(
                'security-check-detail',
                kwargs={'pk': check.pk},
            ),
            format='json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        actual_check_data = response.json()
        self.assertCheckEqual(check, actual_check_data)


class AcceptCheckTestCase(BaseCheckTestCase):
    """
    Tests related to accepting a check.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @mock.patch('security.models.now')
    def test_can_accept_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be accepted.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 4, 1))

        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertEqual(check.actioned_by, authorised_user)
        self.assertEqual(check.actioned_at, mocked_now())

    @mock.patch('security.models.now')
    def test_can_accept_an_accepted_check(self, mocked_now):
        """
        Test that accepting an already accepted check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        check = Check.objects.filter(status=CHECK_STATUS.ACCEPTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
        self.assertNotEqual(check.actioned_at, mocked_now())

    def test_cannot_accept_a_rejected_check(self):
        """
        Test that accepting a rejected check returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.REJECTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-accept',
                kwargs={'pk': check.pk},
            ),
            format='json',
            data={
                'decision_reason': '',
            },
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'status': ['Cannot accept a rejected check.'],
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)


class RejectCheckTestCase(BaseCheckTestCase):
    """
    Tests related to rejecting a check.
    """

    def test_unauthorised_user_gets_403(self):
        """
        Test that if the logged-in user doesn't have permissions, the view returns 403.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        auth = self.get_http_authorization_for_user(self._get_unauthorised_application_user())
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': 'Some reason',
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @mock.patch('security.models.now')
    def test_can_reject_a_pending_check(self, mocked_now):
        """
        Test that a pending check can be rejected.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 4, 1))

        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        reason = 'Some reason'
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': reason,
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertEqual(check.actioned_by, authorised_user)
        self.assertEqual(check.actioned_at, mocked_now())
        self.assertEqual(check.decision_reason, reason)

    @mock.patch('security.models.now')
    def test_can_reject_a_rejected_check(self, mocked_now):
        """
        Test that rejected an already rejected check doesn't do anything.
        """
        mocked_now.return_value = make_aware(datetime.datetime(2019, 1, 1))

        check = Check.objects.filter(status=CHECK_STATUS.REJECTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)
        reason = 'some reason'
        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            data={
                'decision_reason': reason,
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.REJECTED)
        self.assertNotEqual(check.actioned_at, mocked_now())
        self.assertNotEqual(check.decision_reason, reason)

    def test_empty_reason_raises_error(self):
        """
        Test that rejecting a check without reason returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.PENDING).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            {
                'decision_reason': '',
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'decision_reason': ['This field may not be blank.'],
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.PENDING)

    def test_cannot_reject_an_accepted_check(self):
        """
        Test that rejecting a pending check returns status code 400.
        """
        check = Check.objects.filter(status=CHECK_STATUS.ACCEPTED).first()

        authorised_user = self._get_authorised_user()
        auth = self.get_http_authorization_for_user(authorised_user)

        response = self.client.post(
            reverse(
                'security-check-reject',
                kwargs={'pk': check.pk},
            ),
            {
                'decision_reason': 'some reason',
            },
            format='json',
            HTTP_AUTHORIZATION=auth,
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                'status': ['Cannot reject an accepted check.'],
            }
        )

        check.refresh_from_db()

        self.assertEqual(check.status, CHECK_STATUS.ACCEPTED)
