import pathlib

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import File
from django.test import TestCase
from django.urls import reverse_lazy
from model_mommy import mommy

from prison.forms import PrisonerBalanceUploadForm
from prison.models import Prison, PrisonerBalance, PrisonerLocation

User = get_user_model()


class PrisonerBalanceUploadBaseTestCase(TestCase):
    fixtures = ['initial_types', 'test_prisons']
    path_test_csv_folder = pathlib.Path(__file__).parent / 'files'


class PrisonerBalanceUploadFormTestCase(PrisonerBalanceUploadBaseTestCase):
    def parse_file(self, file_name, prison=None):
        if not prison:
            prison = Prison.objects.last()
        prison.use_nomis_for_balances = False
        prison.save()
        file_path = self.path_test_csv_folder / file_name
        with File(file_path.open('rb')) as csv_file:
            form = PrisonerBalanceUploadForm(
                data={'prison': prison.nomis_id},
                files={'csv_file': csv_file},
            )
            form.is_valid()
        return form

    def test_csv_parsed_into_list(self):
        # file contents are formatted as provided in initial sample
        form = self.parse_file('sample-balances.csv')
        self.assertTrue(form.is_valid())
        balances = form.cleaned_data['csv_file']
        self.assertEqual(len(balances), 2)
        self.assertDictEqual(balances[0], {
            'prisoner_number': 'A1409AE',
            'amount': 205377,
        })
        self.assertDictEqual(balances[1], {
            'prisoner_number': 'A1401AE',
            'amount': 3550,
        })

    def test_csv_with_rounded_amounts_parsed_into_list(self):
        # amounts are rounded to whole pounds (could happen if opened and re-saved in Excel for example)
        form = self.parse_file('sample-balances-rounded.csv')
        self.assertTrue(form.is_valid())
        balances = form.cleaned_data['csv_file']
        self.assertEqual(len(balances), 2)
        self.assertDictEqual(balances[0], {
            'prisoner_number': 'A1409AE',
            'amount': 205300,
        })
        self.assertDictEqual(balances[1], {
            'prisoner_number': 'A1401AE',
            'amount': 3500,
        })

    def test_csv_with_no_balances_parsed_into_list(self):
        # no balances, but should be parsed correctly
        form = self.parse_file('sample-balances-no-balances.csv')
        self.assertTrue(form.is_valid())
        balances = form.cleaned_data['csv_file']
        self.assertEqual(len(balances), 0)

    def test_empty_file(self):
        # empty file, but should be parsed correctly even without headers
        form = self.parse_file('sample-balances-empty.csv')
        self.assertTrue(form.is_valid())
        balances = form.cleaned_data['csv_file']
        self.assertEqual(len(balances), 0)

    def test_csv_with_bad_headers(self):
        # unexpected column names
        form = self.parse_file('sample-balances-bad-header.csv')
        self.assertFalse(form.is_valid())

    def test_csv_with_bad_prisoner_number(self):
        # prisoner number in unexpected format
        form = self.parse_file('sample-balances-bad-prisoner-number.csv')
        self.assertFalse(form.is_valid())

    def test_csv_with_bad_amount(self):
        # amount does not turn into whole pence
        form = self.parse_file('sample-balances-bad-amount.csv')
        self.assertFalse(form.is_valid())

    def test_csv_with_negative_amount(self):
        # unexpected negative balance (we don't know if this is possible)
        form = self.parse_file('sample-balances-negative-amount.csv')
        self.assertFalse(form.is_valid())

    def test_unexpected_file_type(self):
        # empty file, therefore expected not to parse
        form = self.parse_file('sample-balances.xlsx')
        self.assertFalse(form.is_valid())

    def test_saves_balances(self):
        # no balances exist yet, try to add 2
        form = self.parse_file('sample-balances.csv')
        self.assertTrue(form.is_valid())
        result = form.save()
        self.assertEqual(result['deleted'], 0)
        self.assertEqual(result['created'], 2)
        self.assertEqual(PrisonerBalance.objects.all().count(), 2)
        self.assertEqual(PrisonerBalance.objects.get(prisoner_number='A1409AE').amount, 205377)

    def test_saves_balances_deleting_all_existing_for_prison(self):
        # 3 balances exist at prison, try to replace with 2 in same prison
        prison = Prison.objects.last()
        for i in range(1, 4):
            PrisonerBalance.objects.create(
                prison=prison,
                prisoner_number=f'A999{i}AA',
                amount=2201,
            )
        form = self.parse_file('sample-balances.csv', prison=prison)
        self.assertTrue(form.is_valid())
        result = form.save()
        self.assertEqual(result['deleted'], 3)
        self.assertEqual(result['created'], 2)
        self.assertEqual(PrisonerBalance.objects.all().count(), 2)
        self.assertEqual(PrisonerBalance.objects.get(prisoner_number='A1409AE').amount, 205377)

    def test_saves_balances_deleting_existing_prisoners(self):
        # 1 balance exist in a prison, try to replace with 2 in another prison
        prison1 = Prison.objects.last()
        PrisonerBalance.objects.create(
            prison=prison1,
            prisoner_number='A1401AE',
            amount=2201,
        )
        prison2 = Prison.objects.exclude(nomis_id=prison1.nomis_id).first()
        self.assertTrue(prison2, msg='There need to be at least 2 test prisons')
        form = self.parse_file('sample-balances.csv', prison=prison2)
        self.assertTrue(form.is_valid())
        result = form.save()
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(result['created'], 2)
        self.assertEqual(PrisonerBalance.objects.all().count(), 2)
        prisoner_balance = PrisonerBalance.objects.get(prisoner_number='A1401AE')
        self.assertEqual(prisoner_balance.amount, 3550)
        self.assertEqual(prisoner_balance.prison, prison2)


class PrisonerBalanceUploadViewTestCase(PrisonerBalanceUploadBaseTestCase):
    url = reverse_lazy('admin:prisoner_balance_upload')

    def test_cannot_access_without_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def login_as_simple_user(self):
        simple_user = User.objects.create(
            username='simple',
            is_staff=True,
            is_superuser=False,
        )
        simple_user.set_password('simple')
        simple_user.save()
        self.client.login(
            username='simple',
            password='simple',
        )

    def test_cannot_access_without_permission(self):
        self.login_as_simple_user()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def login_as_granted_user(self):
        granted_user = User.objects.create(
            username='granted',
            is_staff=True,
            is_superuser=False,
        )
        granted_user.set_password('granted')
        granted_user.save()
        for permission in ['add_prisonerbalance', 'change_prisonerbalance', 'delete_prisonerbalance']:
            permission = Permission.objects.get_by_natural_key(permission, 'prison', 'prisonerbalance')
            granted_user.user_permissions.add(permission)
        self.client.login(
            username='granted',
            password='granted',
        )

    def test_can_access_with_permission(self):
        self.login_as_granted_user()
        response = self.client.get(self.url)
        self.assertContains(response, 'Prisoner balance upload')

    def upload_file(self, file_name, prison):
        self.login_as_granted_user()
        file_path = self.path_test_csv_folder / file_name
        with file_path.open('rb') as csv_file:
            return self.client.post(self.url, data={
                'prison': prison.nomis_id,
                'csv_file': csv_file,
            }, follow=True)

    def test_can_upload_valid_file(self):
        # select a prison
        chosen_prison = Prison.objects.last()
        chosen_prison.use_nomis_for_balances = False
        chosen_prison.save()
        response = self.upload_file('sample-balances.csv', chosen_prison)
        # expect for balances to be saved and no error should show
        self.assertContains(response, 'Saved 2 balances.')
        self.assertEqual(PrisonerBalance.objects.filter(prison=chosen_prison).count(), 2)
        self.assertNotContains(response, 'Was the right prison selected?')

    def test_error_message_if_wrong_prison_likely_selected(self):
        # select a prison
        chosen_prison = Prison.objects.last()
        chosen_prison.use_nomis_for_balances = False
        chosen_prison.save()
        different_prison = Prison.objects.exclude(pk=chosen_prison.pk).first()
        # put all prisoners in sample file into a different prison
        for prisoner_number in ('A1409AE', 'A1401AE'):
            mommy.make(
                PrisonerLocation,
                prison=different_prison,
                prisoner_number=prisoner_number,
                active=True,
            )
        response = self.upload_file('sample-balances.csv', chosen_prison)
        # expect for balances to be saved, but an error should show
        self.assertContains(response, 'Saved 2 balances.')
        self.assertEqual(PrisonerBalance.objects.filter(prison=chosen_prison).count(), 2)
        self.assertContains(response, f'database suggests that most prisoners are likely at {different_prison}')
