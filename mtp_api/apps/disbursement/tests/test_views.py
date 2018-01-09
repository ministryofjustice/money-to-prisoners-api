from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from disbursement.constants import (
    DISBURSEMENT_RESOLUTION, DISBURSEMENT_METHOD, LOG_ACTIONS
)
from disbursement.models import Disbursement, Log
from core.tests.utils import make_test_users
from mtp_auth.models import PrisonUserMapping
from mtp_auth.tests.utils import AuthTestCaseMixin
from prison.models import Prison, PrisonerLocation
from prison.tests.utils import load_random_prisoner_locations


class CreateDisbursementTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _, _, _ = make_test_users()
        load_random_prisoner_locations()

    def test_permissions_required(self):
        user = self.bank_admins[0]

        new_disbursement = {
            'amount': 1000,
            'prisoner_number': 'A1234BC',
            'prison': 'IXB',
            'method': 'bank_transfer',
            'recipient_first_name': 'Sam',
            'recipient_last_name': 'Hall'
        }

        response = self.client.post(
            reverse('disbursement-list'), data=new_disbursement, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_disbursement_succeeds(self):
        user = self.prison_clerks[0]

        prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
        prisoner = PrisonerLocation.objects.filter(prison__in=prisons).first()

        new_disbursement = {
            'amount': 1000,
            'prisoner_number': prisoner.prisoner_number,
            'prison': prisoner.prison.nomis_id,
            'method': 'bank_transfer',
            'recipient_first_name': 'Sam',
            'recipient_last_name': 'Hall'
        }

        response = self.client.post(
            reverse('disbursement-list'), data=new_disbursement, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 1)
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.PENDING)
        self.assertEqual(disbursements[0].method, DISBURSEMENT_METHOD.BANK_TRANSFER)
        self.assertEqual(disbursements[0].prisoner_name, prisoner.prisoner_name)

        logs = Log.objects.all()
        self.assertEqual(logs[0].disbursement, disbursements[0])
        self.assertEqual(logs[0].user, user)
        self.assertEqual(logs[0].action, LOG_ACTIONS.CREATED)

    def test_create_disbursement_fails_for_non_permitted_prison(self):
        user = self.prison_clerks[0]

        prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
        prisoner = PrisonerLocation.objects.exclude(prison__in=prisons).first()

        new_disbursement = {
            'amount': 1000,
            'prisoner_number': prisoner.prisoner_number,
            'prison': prisoner.prison.nomis_id,
            'method': 'bank_transfer',
            'recipient_first_name': 'Sam',
            'recipient_last_name': 'Hall'
        }

        response = self.client.post(
            reverse('disbursement-list'), data=new_disbursement, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 0)

    def test_create_disbursement_fails_for_prisoner_in_different_prison(self):
        user = self.prison_clerks[0]

        prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
        prisoner = PrisonerLocation.objects.exclude(prison__in=prisons).first()

        new_disbursement = {
            'amount': 1000,
            'prisoner_number': prisoner.prisoner_number,
            'prison': prisons.first().nomis_id,
            'method': 'bank_transfer',
            'recipient_first_name': 'Sam',
            'recipient_last_name': 'Hall'
        }

        response = self.client.post(
            reverse('disbursement-list'), data=new_disbursement, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 0)


class ListDisbursementsTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _, _, _ = make_test_users()

    def test_list_disbursements(self):
        user = self.prison_clerks[0]

        Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )
        Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='INP'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        response = self.client.get(
            reverse('disbursement-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['recipient_first_name'], 'Sam')
        self.assertEqual(data['results'][0]['recipient_last_name'], 'Hall')


class UpdateDisbursementsTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _, _, _ = make_test_users()

    def test_update_disbursement(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        response = self.client.patch(
            reverse('disbursement-detail', args=[disbursement.pk]),
            data={'amount': 2000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated = Disbursement.objects.get(pk=disbursement.pk)
        self.assertEqual(updated.amount, 2000)

        logs = Log.objects.all()
        self.assertEqual(logs[0].disbursement, disbursement)
        self.assertEqual(logs[0].user, user)
        self.assertEqual(logs[0].action, LOG_ACTIONS.EDITED)

    def test_cannot_update_resolution(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        response = self.client.patch(
            reverse('disbursement-detail', args=[disbursement.pk]),
            data={'resolution': DISBURSEMENT_RESOLUTION.SENT}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated = Disbursement.objects.get(pk=disbursement.pk)
        self.assertEqual(updated.resolution, DISBURSEMENT_RESOLUTION.PENDING)

        self.assertEqual(Log.objects.all().count(), 0)

    def test_cannot_update_disbursement_for_different_prison(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='INP'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        response = self.client.patch(
            reverse('disbursement-detail', args=[disbursement.pk]),
            data={'amount': 2000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        updated = Disbursement.objects.get(pk=disbursement.pk)
        self.assertEqual(updated.amount, 1000)

        self.assertEqual(Log.objects.all().count(), 0)

    def test_cannot_update_non_pending_disbursement(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
            resolution=DISBURSEMENT_RESOLUTION.CONFIRMED
        )

        response = self.client.patch(
            reverse('disbursement-detail', args=[disbursement.pk]),
            data={'amount': 2000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        updated = Disbursement.objects.get(pk=disbursement.pk)
        self.assertEqual(updated.amount, 1000)

        self.assertEqual(Log.objects.all().count(), 0)


class UpdateDisbursementResolutionTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _, _, _ = make_test_users()

    def test_reject_disbursement(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        self.assertEqual(disbursement.resolution, DISBURSEMENT_RESOLUTION.PENDING)

        response = self.client.post(
            reverse('disbursement-reject'),
            data={'disbursement_ids': [disbursement.id]}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 1)
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.REJECTED)

        logs = Log.objects.all()
        self.assertEqual(logs[0].disbursement, disbursements[0])
        self.assertEqual(logs[0].user, user)
        self.assertEqual(logs[0].action, LOG_ACTIONS.REJECTED)

    def test_can_only_confirm_preconfirmed_disbursement(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
            resolution=DISBURSEMENT_RESOLUTION.PENDING
        )

        response = self.client.post(
            reverse('disbursement-confirm'), format='json',
            data=[{'id': disbursement.id, 'nomis_transaction_id': 111}],
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['errors'][0]['ids'],
            [disbursement.id]
        )

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.PENDING)

        self.assertEqual(Log.objects.all().count(), 0)

    def test_confirm_disbursement(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
            resolution=DISBURSEMENT_RESOLUTION.PRECONFIRMED
        )

        response = self.client.post(
            reverse('disbursement-confirm'), format='json',
            data=[{'id': disbursement.id, 'nomis_transaction_id': '1112-1'}],
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        confirmed_disbursement = Disbursement.objects.get(pk=disbursement.id)
        self.assertEqual(
            confirmed_disbursement.resolution,
            DISBURSEMENT_RESOLUTION.CONFIRMED
        )
        self.assertEqual(
            confirmed_disbursement.nomis_transaction_id,
            '1112-1'
        )

        logs = Log.objects.all()
        self.assertEqual(logs[0].disbursement, confirmed_disbursement)
        self.assertEqual(logs[0].user, user)
        self.assertEqual(logs[0].action, LOG_ACTIONS.CONFIRMED)

    def test_cannot_reject_disbursement_for_non_permitted_prison(self):
        user = self.prison_clerks[0]

        disbursement = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='INP'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall'
        )

        self.assertEqual(disbursement.resolution, DISBURSEMENT_RESOLUTION.PENDING)

        response = self.client.post(
            reverse('disbursement-reject'),
            data={'disbursement_ids': [disbursement.id]}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 1)
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.PENDING)

        self.assertEqual(Log.objects.all().count(), 0)

    def test_send_disbursement(self):
        user = self.bank_admins[0]

        disbursement1 = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
            resolution=DISBURSEMENT_RESOLUTION.CONFIRMED
        )
        disbursement2 = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BD',
            prison=Prison.objects.get(pk='INP'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
            resolution=DISBURSEMENT_RESOLUTION.CONFIRMED
        )

        response = self.client.post(
            reverse('disbursement-send'),
            data={'disbursement_ids': [disbursement1.id, disbursement2.id]},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 2)
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.SENT)
        self.assertEqual(disbursements[1].resolution, DISBURSEMENT_RESOLUTION.SENT)

        logs = Log.objects.all()
        self.assertEqual(logs[0].disbursement, disbursements[0])
        self.assertEqual(logs[0].user, user)
        self.assertEqual(logs[0].action, LOG_ACTIONS.SENT)
        self.assertEqual(logs[1].disbursement, disbursements[1])
        self.assertEqual(logs[1].user, user)
        self.assertEqual(logs[1].action, LOG_ACTIONS.SENT)

    def test_cannot_send_unconfirmed_disbursement(self):
        user = self.bank_admins[0]

        disbursement1 = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BC',
            prison=Prison.objects.get(pk='IXB'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
        )
        disbursement2 = Disbursement.objects.create(
            amount=1000,
            prisoner_number='A1234BD',
            prison=Prison.objects.get(pk='INP'),
            method=DISBURSEMENT_METHOD.BANK_TRANSFER,
            recipient_first_name='Sam',
            recipient_last_name='Hall',
        )

        response = self.client.post(
            reverse('disbursement-send'),
            data={'disbursement_ids': [disbursement1.id, disbursement2.id]},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

        disbursements = Disbursement.objects.all()
        self.assertEqual(disbursements.count(), 2)
        self.assertEqual(disbursements[0].resolution, DISBURSEMENT_RESOLUTION.PENDING)
        self.assertEqual(disbursements[1].resolution, DISBURSEMENT_RESOLUTION.PENDING)

        self.assertEqual(Log.objects.all().count(), 0)
