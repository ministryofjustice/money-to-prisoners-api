from django.core.management import call_command

from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase
from security.models import (
    BankAccount, DebitCardSenderDetails, PrisonerProfile
)


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
