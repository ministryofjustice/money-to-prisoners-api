import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.urlresolvers import reverse
from django.db import models
from django.test import TestCase
from django.utils.timezone import now

from core.tests.utils import make_test_users
from transaction.constants import TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions
from transaction.utils import format_amount

User = get_user_model()


class DashboardTestCase(TestCase):
    fixtures = ['initial_groups.json', 'test_prisons.json']

    def test_permissions(self):
        dashboard_url = reverse('admin:dashboard')
        user_details = dict(username='a_user', password='a_user')

        user = User.objects.create_user(**user_details)
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)

        user.is_staff = True
        user.save()
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)

        view_dashboard = Permission.objects.get_by_natural_key('view_dashboard', 'transaction', 'transaction')
        user.user_permissions.add(view_dashboard)
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        user.user_permissions.clear()
        user.is_superuser = True
        user.save()
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_transaction_report(self):
        make_test_users(clerks_per_prison=1)
        self.transactions = generate_transactions(transaction_batch=50,
                                                  only_new_transactions=True)
        self.superuser = User.objects.create_superuser(username='admin', password='admin',
                                                       email='admin@mtp.local')
        self.client.login(username='admin', password='admin')

        response = self.client.get(reverse('admin:dashboard'))

        self.assertContains(response, 'Today’s transaction report')
        yesterday = (now() - datetime.timedelta(days=1)).date()
        todays_transactions = Transaction.objects.filter(received_at__date=yesterday)
        available_transactions = todays_transactions.filter(
            **Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.AVAILABLE]
        )
        available = available_transactions.aggregate(amount=models.Sum('amount'))['amount'] or 0
        response_content = response.content.decode(response.charset)
        self.assertIn(format_amount(available, trim_empty_pence=True), response_content)
