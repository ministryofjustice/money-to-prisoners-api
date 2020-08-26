import random

from django.db import connection
from rest_framework import status

from credit.models import Credit
from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListOrderingTestCase(CreditListTestCase):
    transaction_batch = 200

    @classmethod
    def setUpClass(cls):
        with connection.cursor() as cursor:
            # forces C collation to order names without ignoring spaces on RDS
            cursor.execute(
                """
                ALTER TABLE %(table_name)s
                ALTER COLUMN prisoner_name
                SET DATA TYPE CHARACTER VARYING(%(prisoner_name_len)d) COLLATE "C";
                """ % {
                    'table_name': Credit._meta.db_table,
                    'prisoner_name_len': Credit._meta.get_field('prisoner_name').max_length,
                }
            )
        super().setUpClass()

    def setUp(self):
        super().setUp()
        credit_1 = Credit.objects.first()
        credit_2 = Credit.objects.exclude(prisoner_name=credit_1.prisoner_name).first()
        Credit.objects.filter(prisoner_name=credit_1.prisoner_name).update(prisoner_name='LEON PETERS')
        Credit.objects.filter(prisoner_name=credit_2.prisoner_name).update(prisoner_name='LEONARD CARTER')
        self.logged_in_user = self._get_authorised_user()

    @classmethod
    def add_test_methods(cls):
        for ordering_field in ['received_at', 'amount', 'prisoner_number', 'prisoner_name']:
            cls.add_test_method(ordering_field)

    @classmethod
    def add_test_method(cls, ordering):
        def test_method(self):
            response = self._test_ordering(ordering)
            response_reversed = self._test_ordering('-' + ordering)
            self.assertEqual(response.data['count'], response_reversed.data['count'])

            search = ''
            while not search:
                credit = random.choice(self.credits)
                if credit.prison in self.logged_in_user.prisonusermapping.prisons.all() and credit.prisoner_name:
                    search = credit.prisoner_name[:-4].strip()
            self._test_ordering(ordering, prisoner_name=search.lower())

        setattr(cls, 'test_ordering_by_' + ordering, test_method)

    def _test_ordering(self, ordering, **filters):
        url = self._get_url(ordering=ordering, **filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']
        if len(results) < 2:
            print('Cannot test ordering on a list of fewer than 2 results')
            return
        if ordering.startswith('-'):
            ordering = ordering[1:]
            results = reversed(results)
        last_item = None
        for item in results:
            if last_item is not None:
                self.assertGreaterEqual(item[ordering], last_item[ordering])
            last_item = item
        return response


CreditListOrderingTestCase.add_test_methods()
