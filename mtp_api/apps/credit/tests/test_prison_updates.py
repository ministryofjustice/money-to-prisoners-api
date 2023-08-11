from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users

from prison.models import Prison, PrisonerLocation
from prison.tests.utils import random_prisoner_number, random_prisoner_dob, random_prisoner_name

from credit.constants import CREDIT_RESOLUTION
from credit.signals import credit_prisons_need_updating
from credit.models import Credit
from transaction.models import Transaction
from payment.models import Payment

User = get_user_model()


class BaseUpdatePrisonsTestCase(TestCase):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json'
    ]

    def _get_credit_data(self):
        return {
            'amount': 1000,
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'prison': None,
            'received_at': timezone.now().replace(microsecond=0),
        }

    def setUp(self):
        super().setUp()
        make_test_users()

        self.credit = Credit.objects.create(
            **self._get_credit_data()
        )


class BaseUpdatePrisonsForTransactionsTestCase(BaseUpdatePrisonsTestCase):
    def setUp(self):
        super().setUp()

        self.transaction = Transaction.objects.create(
            amount=self.credit.amount,
            received_at=self.credit.received_at,
            credit=self.credit
        )


class BaseUpdatePrisonsForPaymentsTestCase(BaseUpdatePrisonsTestCase):
    def setUp(self):
        super().setUp()

        self.payment = Payment.objects.create(
            amount=self.credit.amount,
            credit=self.credit
        )


class UpdatePrisonsOnAvailableCreditsTestMixin:
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': Prison.objects.first(),
            'owner': None,
            'resolution': CREDIT_RESOLUTION.PENDING,
        })
        return data

    def test_with_prisoner_locations_updates_prison(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        new_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=new_prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison.pk, new_prison.pk)
        self.assertEqual(self.credit.prisoner_name, prisoner_name)

    def test_updates_to_active_location_when_inactive_duplicate_exists(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        new_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=new_prison,
            active=False
        )
        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=existing_prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison.pk, existing_prison.pk)
        self.assertEqual(self.credit.prisoner_name, prisoner_name)


class UpdatePrisonsOnAvailableTransactionsTestCase(
    UpdatePrisonsOnAvailableCreditsTestMixin, BaseUpdatePrisonsForTransactionsTestCase
):
    def test_without_prisoner_locations_sets_prison_to_none(self):
        self.assertNotEqual(self.credit.prison, None)

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison, None)

    def test_with_inactive_prisoner_locations_sets_prison_to_none(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        new_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=new_prison,
            active=False
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison, None)


class UpdatePrisonsOnAvailablePaymentsTestCase(
    UpdatePrisonsOnAvailableCreditsTestMixin, BaseUpdatePrisonsForPaymentsTestCase
):
    def test_without_prisoner_locations_does_not_set_prison_to_none(self):
        self.assertNotEqual(self.credit.prison, None)

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertNotEqual(self.credit.prison, None)

    def test_with_inactive_prisoner_locations_does_not_set_prison_to_none(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        new_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=new_prison,
            active=False
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertNotEqual(self.credit.prison, None)


class UpdatePrisonsOnLockedCreditsTestCase(BaseUpdatePrisonsForPaymentsTestCase):
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'owner': User.objects.first(),
            'resolution': CREDIT_RESOLUTION.PENDING,
        })
        return data

    def test_prisoner_location_doesnt_update_credit(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=other_prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison.pk, existing_prison.pk)
        self.assertNotEqual(self.credit.prisoner_name, new_prisoner_name)


class UpdatePrisonsOnCreditedCreditsTestcase(BaseUpdatePrisonsForTransactionsTestCase):
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'owner': User.objects.first(),
            'resolution': CREDIT_RESOLUTION.CREDITED,
        })
        return data

    def test_prisoner_location_doesnt_update_credit(self):
        self.assertNotEqual(self.credit.prison, None)

        existing_prison = self.credit.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=other_prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertNotEqual(self.credit.prisoner_name, new_prisoner_name)
        self.assertEqual(self.credit.prison.pk, existing_prison.pk)


class UpdatePrisonsOnRefundedCreditsTestcase(BaseUpdatePrisonsForTransactionsTestCase):
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': None,
            'owner': None,
            'resolution': CREDIT_RESOLUTION.REFUNDED,
        })
        return data

    def test_prisoner_location_doesnt_update_credit(self):
        self.assertEqual(self.credit.prison, None)
        self.assertTrue(self.credit.refunded)

        prison = Prison.objects.first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison, None)
        self.assertEqual(self.credit.prisoner_name, None)
        self.assertTrue(self.credit.refunded)


class UpdatePrisonsOnRefundPendingCreditsTestcase(BaseUpdatePrisonsForTransactionsTestCase):
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': None,
            'owner': None,
            'resolution': CREDIT_RESOLUTION.PENDING,
        })
        return data

    def test_without_prisoner_locations_doesnt_set_prison(self):
        self.assertEqual(self.credit.prison, None)

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison, None)

    def test_with_prisoner_locations_sets_prison(self):
        self.assertEqual(self.credit.prison, None)

        prison = Prison.objects.first()
        prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertEqual(self.credit.prison.pk, prison.pk)
        self.assertEqual(self.credit.prisoner_name, prisoner_name)


class UpdatePrisonsOnReconciledCreditsTestcase(BaseUpdatePrisonsForTransactionsTestCase):
    def _get_credit_data(self):
        data = super()._get_credit_data()
        data.update({
            'prison': Prison.objects.first(),
            'prisoner_name': random_prisoner_name(),
            'owner': None,
            'resolution': CREDIT_RESOLUTION.PENDING,
            'reconciled': True
        })
        return data

    def test_prisoner_location_doesnt_update_credit(self):
        existing_prison = self.credit.prison
        other_prison = Prison.objects.exclude(pk=existing_prison.pk).first()
        new_prisoner_name = random_prisoner_name()

        PrisonerLocation.objects.create(
            created_by=User.objects.first(),
            prisoner_name=new_prisoner_name,
            prisoner_number=self.credit.prisoner_number,
            prisoner_dob=self.credit.prisoner_dob,
            prison=other_prison,
            active=True
        )

        credit_prisons_need_updating.send(sender=None)

        self.credit.refresh_from_db()
        self.assertNotEqual(self.credit.prisoner_name, new_prisoner_name)
        self.assertEqual(self.credit.prison.pk, existing_prison.pk)
