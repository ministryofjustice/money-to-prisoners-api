import datetime

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.forms import MediaDefiningClass
from django.utils.dateformat import format as format_date
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from account.models import Balance
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE
from transaction.models import Transaction
from transaction.utils import format_amount, format_number


class DashboardModule(metaclass=MediaDefiningClass):
    template = 'core/dashboard/module.html'
    html_classes = 'module'
    title = _('Dashboard')
    enabled = True

    def __init__(self, dashboard_view):
        self.dashboard_view = dashboard_view


class TransactionReport(DashboardModule):
    template = 'core/dashboard/transaction-report.html'
    title = _('Transaction report')
    column_count = 3

    class Media:
        css = {
            'all': ('core/css/transaction-report.css',)
        }

    def __init__(self, dashboard_view, received_at=None):
        super().__init__(dashboard_view)
        if not received_at:
            try:
                received_at = Transaction.objects.latest().received_at.date()
            except Transaction.DoesNotExist:
                received_at = (now() - datetime.timedelta(days=1)).date()
            self.title = _('Latest transactions received %(date)s') % {
                'date':  format_date(received_at, 'j N')
            }
        if isinstance(received_at, (list, tuple)):
            received_at = list(map(
                lambda d: d.date() if isinstance(d, datetime.datetime) else d,
                received_at
            ))
            self.transaction_filters = {
                'received_at__date__gte': received_at[0],
                'received_at__date__lte': received_at[1],
            }
            filter_string = 'received_at__date__gte=%s&' \
                            'received_at__date__lte=%s' % (received_at[0].isoformat(),
                                                           received_at[1].isoformat())
        else:
            self.transaction_filters = {
                'received_at__date': received_at
            }
            filter_string = 'received_at__day=%d&' \
                            'received_at__month=%d&' \
                            'received_at__year=%d' % (received_at.day,
                                                      received_at.month,
                                                      received_at.year)
        if self.dashboard_view.request.user.has_perm('transaction.change_transaction'):
            self.change_list_url = reverse('admin:transaction_transaction_changelist') + '?' + filter_string
        self.queryset = Transaction.objects.filter(**self.transaction_filters)

    @classmethod
    def get_current_balance(cls):
        value = getattr(Balance.objects.first(), 'closing_balance', None)
        return format_amount(value, trim_empty_pence=True) or '—'

    @classmethod
    def get_count(cls, queryset):
        value = queryset.count()
        if value is None:
            return '—'
        if isinstance(value, (int, float)):
            return format_number(value)
        return value

    @classmethod
    def get_amount_sum(cls, queryset):
        value = queryset.aggregate(amount=models.Sum('amount')).get('amount')
        return format_amount(value, trim_empty_pence=True) or '—'

    @property
    def valid_credits(self):
        return self.queryset.filter(
            prison__isnull=False,
            category=TRANSACTION_CATEGORY.CREDIT,
            source__in=[
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE,
            ],
        )

    @property
    def credits_to_refund(self):
        return self.queryset.filter(
            prison__isnull=True,
            incomplete_sender_info=False,
            category=TRANSACTION_CATEGORY.CREDIT,
            source=TRANSACTION_SOURCE.BANK_TRANSFER,
        )

    @property
    def unidentified_credits(self):
        return self.queryset.filter(
            prison__isnull=True,
            incomplete_sender_info=True,
            category=TRANSACTION_CATEGORY.CREDIT,
            source=TRANSACTION_SOURCE.BANK_TRANSFER,
        )

    @property
    def credited_payments(self):
        return self.queryset.filter(
            credited=True,
            category=TRANSACTION_CATEGORY.CREDIT,
            source__in=[
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE,
            ],
        )

    @property
    def refunded_payments(self):
        return self.queryset.filter(
            refunded=True,
            category=TRANSACTION_CATEGORY.CREDIT,
            source=TRANSACTION_SOURCE.BANK_TRANSFER,
        )

    def get_table(self):
        return [
            {
                'title': _('Valid credits'),
                'value': self.get_amount_sum(self.valid_credits),
            },
            {
                'title': _('Credits to refund'),
                'value': self.get_amount_sum(self.credits_to_refund),
            },
            {
                'title': _('Curent balance'),
                'value': self.get_current_balance(),
            },
            {
                'title': _('Valid credits'),
                'value': self.get_count(self.valid_credits),
            },
            {
                'title': _('Credits to refund'),
                'value': self.get_count(self.credits_to_refund),
            },
            {
                'title': _('Unidentified credits'),
                'value': self.get_count(self.unidentified_credits),
                'help_text': _('Credits that do not match an offender in the system and cannot be refunded'),
            },
            {
                'title': _('Credited'),
                'value': self.get_count(self.credited_payments),
                'help_text': _('Credited through the Cashbook tool'),
            },
            {
                'title': _('Refunded'),
                'value': self.get_count(self.refunded_payments),
                'help_text': _('Refunds file downloaded through the Bank Admin tool'),
            },
        ]


class ExternalDashboards(DashboardModule):
    template = 'core/dashboard/external-dashboards.html'
    title = _('External dashboards and logs')
    apps = [
        'api', 'cashbook', 'bank-admin', 'prisoner-location-admin',
        'transaction-uploader', 'send-money',
    ]

    def __init__(self, dashboard_view):
        super().__init__(dashboard_view)
        if settings.ENVIRONMENT == 'test':
            self.grafana_host = 'grafana-staging.service.dsd.io'
            self.kibana_host = 'kibana-staging.service.dsd.io'
        elif settings.ENVIRONMENT == 'prod':
            self.grafana_host = 'grafana.service.dsd.io'
            self.kibana_host = 'kibana.service.dsd.io'
        else:
            self.grafana_host = None
            self.kibana_host = None
            self.enabled = False
        self.kibana_params = '_g=(time:(from:now-24h,mode:quick,to:now))'  # last 24 hours

    def get_table(self):
        return [
            {
                'title': _('Application dashboard'),
                'links': [
                    {
                        'title': _('All apps'),
                        'url': 'https://%s/#/dashboard/MTP?%s' % (self.kibana_host, self.kibana_params)
                    }
                ],
            },
            {
                'title': _('Application logs'),
                'links': self.make_app_links('https://%(kibana_host)s/#/discover/MTP-%(app)s'
                                             '?%(kibana_params)s'),
            },
            {
                'title': _('Host machine dashboards'),
                'links': self.make_app_links('https://%(grafana_host)s/dashboard/db/mtp'
                                             '?var-project=moneytoprisoners-%(app)s'),
            },
        ]

    def make_app_links(self, link_template):
        return [
            {
                'title': app,
                'url': link_template % {
                    'grafana_host': self.grafana_host,
                    'kibana_host': self.kibana_host,
                    'kibana_params': self.kibana_params,
                    'app': app,
                }
            }
            for app in self.apps
        ]
