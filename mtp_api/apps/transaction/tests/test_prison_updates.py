from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from core.tests.utils import make_test_users

from prison.models import Prison, PrisonerLocation
from prison.tests.utils import random_prisoner_number, random_prisoner_dob,\
    random_prisoner_name

from transaction.models import Transaction
from transaction.signals import transaction_prisons_need_updating


class BaseUpdatePrisonsTestCase(TestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]

    def _get_transaction_data(self):
        return {
            'amount': 1000,
            'prison': None,
            'received_at': timezone.now().replace(microsecond=0),
            'sender_sort_code': '123456',
            'sender_account_number': '12345678',
            'sender_name': 'Sender Name'
        }

    def setUp(self):
        super(BaseUpdatePrisonsTestCase, self).setUp()
        make_test_users()

        self.transaction = Transaction.objects.create(
            **self._get_transaction_data()
        )


class UpdatePrisonsOnAvailableTransactionsTestCase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnAvailableTransactionsTestCase, self)._get_transaction_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': None,
            'credited': False,
            'refunded': False
        })
        return data

    def test_without_prisoner_locations_sets_prison_to_None(self):
        self.assertNotEqual(self.transaction.prison, None)

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison, None)

    def test_with_prisoner_locations_overrides_prison(self):
        self.assertNotEqual(self.transaction.prison, None)

        existing_prison = self.transaction.prison
        new_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=new_prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison.pk, new_prison.pk)
        self.assertEqual(self.transaction.prisoner_name, prisoner_name)


class UpdatePrisonsOnLockedTransactionsTestCase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnLockedTransactionsTestCase, self)._get_transaction_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': User.objects.first(),
            'credited': False,
            'refunded': False
        })
        return data

    def test_prisoner_location_doesnt_update_transaction(self):
        self.assertNotEqual(self.transaction.prison, None)

        existing_prison = self.transaction.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=other_prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison.pk, existing_prison.pk)
        self.assertNotEqual(self.transaction.prisoner_name, new_prisoner_name)


class UpdatePrisonsOnCreditedTransactionsTestcase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnCreditedTransactionsTestcase, self)._get_transaction_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': User.objects.first(),
            'credited': True,
            'refunded': False
        })
        return data

    def test_prisoner_location_doesnt_update_transaction(self):
        self.assertNotEqual(self.transaction.prison, None)

        existing_prison = self.transaction.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=other_prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertNotEqual(self.transaction.prisoner_name, new_prisoner_name)
        self.assertEqual(self.transaction.prison.pk, existing_prison.pk)


class UpdatePrisonsOnRefundedTransactionsTestcase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnRefundedTransactionsTestcase, self)._get_transaction_data()
        data.update({
            'prison': None,
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': None,
            'credited': False,
            'refunded': True
        })
        return data

    def test_prisoner_location_doesnt_update_transaction(self):
        self.assertEqual(self.transaction.prison, None)
        self.assertTrue(self.transaction.refunded)

        prison = Prison.objects.first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison, None)
        self.assertEqual(self.transaction.prisoner_name, None)
        self.assertTrue(self.transaction.refunded)


class UpdatePrisonsOnRefundPendingTransactionsTestcase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnRefundPendingTransactionsTestcase, self)._get_transaction_data()
        data.update({
            'prison': None,
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': None,
            'credited': False,
            'refunded': False
        })
        return data

    def test_without_prisoner_locations_doesnt_set_prison(self):
        self.assertEqual(self.transaction.prison, None)

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison, None)

    def test_with_prisoner_locations_sets_prison(self):
        self.assertEqual(self.transaction.prison, None)

        prison = Prison.objects.first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.prison.pk, prison.pk)
        self.assertEqual(self.transaction.prisoner_name, prisoner_name)


class UpdatePrisonsOnReconciledTransactionsTestcase(BaseUpdatePrisonsTestCase):

    def _get_transaction_data(self):
        data = super(UpdatePrisonsOnReconciledTransactionsTestcase, self)._get_transaction_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'owner': None,
            'credited': False,
            'refunded': False,
            'reconciled': True
        })
        return data

    def test_prisoner_location_doesnt_update_transaction(self):
        existing_prison = self.transaction.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.transaction.prisoner_number,
            prisoner_dob=self.transaction.prisoner_dob,
            prison=other_prison
        )

        transaction_prisons_need_updating.send(sender=None)

        self.transaction.refresh_from_db()
        self.assertNotEqual(self.transaction.prisoner_name, new_prisoner_name)
        self.assertEqual(self.transaction.prison.pk, existing_prison.pk)
