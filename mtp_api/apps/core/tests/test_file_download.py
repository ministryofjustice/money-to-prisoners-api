from datetime import date

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import FileDownload
from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin


BANK_STATEMENT_LABEL = 'BANK_STATEMENT'


class CreateFileDownloadTestCase(AuthTestCaseMixin, APITestCase):

    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.bank_admins = test_users['bank_admins']

    def test_create_file_download_succeeds(self):
        user = self.bank_admins[0]

        new_file_download = {
            'label': BANK_STATEMENT_LABEL,
            'date': date.today()
        }

        response = self.client.post(
            reverse('filedownload-list'), data=new_file_download, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        file_downloads = FileDownload.objects.all()
        self.assertEqual(file_downloads.count(), 1)
        self.assertEqual(file_downloads[0].label, BANK_STATEMENT_LABEL)
        self.assertEqual(file_downloads[0].date, date.today())

    def test_create_file_download_only_allows_one_per_label_per_date(self):
        user = self.bank_admins[0]
        download_date = date.today()

        new_file_download = {
            'label': BANK_STATEMENT_LABEL,
            'date': download_date
        }
        response = self.client.post(
            reverse('filedownload-list'), data=new_file_download, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        new_file_download = {
            'label': BANK_STATEMENT_LABEL,
            'date': download_date
        }
        response = self.client.post(
            reverse('filedownload-list'), data=new_file_download, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        file_downloads = FileDownload.objects.all()
        self.assertEqual(file_downloads.count(), 1)
        self.assertEqual(file_downloads[0].label, BANK_STATEMENT_LABEL)
        self.assertEqual(file_downloads[0].date, download_date)


class MissingFileDownloadTestCase(AuthTestCaseMixin, APITestCase):

    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.bank_admins = test_users['bank_admins']

    def _create_existing_file_downloads(self):
        FileDownload(label=BANK_STATEMENT_LABEL, date=date(2018, 2, 5)).save()
        FileDownload(label=BANK_STATEMENT_LABEL, date=date(2018, 2, 6)).save()
        FileDownload(label=BANK_STATEMENT_LABEL, date=date(2018, 2, 8)).save()
        FileDownload(label=BANK_STATEMENT_LABEL, date=date(2018, 2, 10)).save()

    def test_missing_file_downloads_returned(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'label': BANK_STATEMENT_LABEL,
            'date': ['2018-02-06', '2018-02-07', '2018-02-08', '2018-02-09']
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {'missing_dates': ['2018-02-07', '2018-02-09']}
        )

    def test_empty_response_for_all_present(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'label': BANK_STATEMENT_LABEL,
            'date': ['2018-02-05', '2018-02-06']
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {'missing_dates': []}
        )

    def test_error_for_invalid_date(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'label': BANK_STATEMENT_LABEL,
            'date': ['2018-02-05', '201-02-06']
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_error_for_missing_label(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'date': ['2018-02-05', '2018-02-06']
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_error_for_missing_dates(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'label': BANK_STATEMENT_LABEL
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cuts_off_at_earliest_record(self):
        user = self.bank_admins[0]
        self._create_existing_file_downloads()

        params = {
            'label': BANK_STATEMENT_LABEL,
            'date': [
                '2018-02-03', '2018-02-04', '2018-02-05', '2018-02-06',
                '2018-02-07', '2018-02-08', '2018-02-09'
            ]
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {'missing_dates': ['2018-02-07', '2018-02-09']}
        )

    def test_returns_empty_if_no_records_with_label_exist(self):
        user = self.bank_admins[0]

        params = {
            'label': BANK_STATEMENT_LABEL,
            'date': [
                '2018-02-03', '2018-02-04', '2018-02-05', '2018-02-06',
                '2018-02-07', '2018-02-08', '2018-02-09'
            ]
        }
        response = self.client.get(
            reverse('filedownload-missing'), params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {'missing_dates': []}
        )
