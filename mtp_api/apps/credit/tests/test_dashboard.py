import datetime
import json

from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse_lazy
from django.db import models
from django.utils.timezone import now

from core.views import DashboardView
from core.tests.test_dashboard import DashboardTestCase
from core.tests.utils import make_test_users
from credit.dashboards import CreditReport, CREDITABLE_FILTERS
from credit.models import Credit
from prison.tests.utils import load_random_prisoner_locations
from transaction.tests.utils import generate_transactions
from transaction.utils import format_amount

User = get_user_model()


class TransactionDashboardTestCase(DashboardTestCase):
    fixtures = ['initial_groups.json', 'initial_types.json', 'test_prisons.json']
    url = reverse_lazy('admin:dashboard')

    def setUp(self):
        super().setUp()
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=50)
        self.superuser = User.objects.create_superuser(username='admin', password='adminadmin',
                                                       email='admin@mtp.local')
        self.client.login(username='admin', password='adminadmin')

    def assertAmountInContent(self, amount, response):  # noqa
        if amount:
            creditable_amount = format_amount(amount, trim_empty_pence=True)
        else:
            creditable_amount = '—'
        response_content = response.content.decode(response.charset)
        self.assertIn(creditable_amount, response_content)

    def test_transaction_report(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'This week')
        start_of_week = now()
        start_of_week = start_of_week - datetime.timedelta(days=start_of_week.isoweekday() - 1)
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        credit_set = Credit.objects.filter(CREDITABLE_FILTERS).filter(
            received_at__range=(start_of_week, now())
        )
        credited_amount = credit_set.aggregate(amount=models.Sum('amount'))['amount']
        self.assertAmountInContent(credited_amount, response)

        self.client.cookies[DashboardView.cookie_name] = json.dumps({
            CreditReport.cookie_key: 'date_range=all'
        })
        response = self.client.get(self.url)
        self.assertContains(response, 'Since the beginning')
        credit_set = Credit.objects.filter(CREDITABLE_FILTERS)
        credited_amount = credit_set.aggregate(amount=models.Sum('amount'))['amount']
        self.assertAmountInContent(credited_amount, response)
