import json

from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.timezone import localtime

from core.views import DashboardView
from core.tests.test_dashboard import DashboardTestCase
from core.tests.utils import make_test_users
from transaction.constants import TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions
from transaction.dashboards import TransactionReport
from transaction.utils import format_amount

User = get_user_model()


class TransactionDashboardTestCase(DashboardTestCase):
    fixtures = ['initial_groups.json', 'test_prisons.json']

    def assertAmountInContent(self, amount, response):  # noqa
        if amount:
            creditable_amount = format_amount(amount, trim_empty_pence=True)
        else:
            creditable_amount = '—'
        response_content = response.content.decode(response.charset)
        self.assertIn(creditable_amount, response_content)

    def test_transaction_report(self):
        make_test_users(clerks_per_prison=1)
        generate_transactions(transaction_batch=50,
                              only_new_transactions=True)
        self.superuser = User.objects.create_superuser(username='admin', password='admin',
                                                       email='admin@mtp.local')
        self.client.login(username='admin', password='admin')
        url = reverse('admin:dashboard')

        response = self.client.get(url)
        self.assertContains(response, 'Latest transactions received on')
        transactions = Transaction.objects.filter(
            Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITABLE],
            received_at__date=localtime(Transaction.objects.latest().received_at).date()
        )
        creditable_amount = transactions.aggregate(amount=models.Sum('amount'))['amount']
        self.assertAmountInContent(creditable_amount, response)

        self.client.cookies[DashboardView.cookie_name] = json.dumps({
            TransactionReport.cookie_key: 'date_range=all'
        })
        response = self.client.get(url)
        self.assertContains(response, 'All transactions')
        transactions = Transaction.objects.filter(
            Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITABLE]
        )
        creditable_amount = transactions.aggregate(amount=models.Sum('amount'))['amount']
        self.assertAmountInContent(creditable_amount, response)
