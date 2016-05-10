from django.db import models
from model_utils.models import TimeStampedModel

from credit.models import Credit
from .constants import (
    TRANSACTION_STATUS, TRANSACTION_CATEGORY, TRANSACTION_SOURCE
)
from .managers import TransactionQuerySet
from .utils import format_amount


class Transaction(TimeStampedModel):
    amount = models.PositiveIntegerField()
    category = models.CharField(max_length=50, choices=TRANSACTION_CATEGORY)
    source = models.CharField(max_length=50, choices=TRANSACTION_SOURCE)

    processor_type_code = models.CharField(max_length=12, blank=True, null=True)
    sender_sort_code = models.CharField(max_length=50, blank=True)
    sender_account_number = models.CharField(max_length=50, blank=True)
    sender_name = models.CharField(max_length=250, blank=True)

    # used by building societies to identify the account nr
    sender_roll_number = models.CharField(blank=True, max_length=50)

    # original reference
    reference = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now=False)

    # 6-digit reference code for reconciliation
    ref_code = models.CharField(max_length=12, null=True)

    incomplete_sender_info = models.BooleanField(default=False)
    reference_in_sender_field = models.BooleanField(default=False)

    credit = models.OneToOneField(Credit, on_delete=models.CASCADE, null=True)

    # NB: there are matching boolean fields or properties on the model instance for each
    STATUS_LOOKUP = {
        TRANSACTION_STATUS.CREDITABLE: {
            'credit__prison__isnull': False
        },
        TRANSACTION_STATUS.REFUNDABLE: {
            'credit__isnull': False,
            'credit__prison__isnull': True,
            'incomplete_sender_info': False
        },
        TRANSACTION_STATUS.UNIDENTIFIED: {
            'credit__prison__isnull': True,
            'incomplete_sender_info': True,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.BANK_TRANSFER
        },
        TRANSACTION_STATUS.ANOMALOUS: {
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.ADMINISTRATIVE
        }
    }

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ('received_at',)
        get_latest_by = 'received_at'
        permissions = (
            ('view_transaction', 'Can view transaction'),
            ('view_dashboard', 'Can view dashboard'),
            ('view_bank_details_transaction', 'Can view bank details of transaction'),
            ('patch_processed_transaction', 'Can patch processed transaction'),
        )

    def __str__(self):
        return 'Transaction {id}, {amount} {sender_name} > {prisoner_name}, {status}'.format(
            id=self.pk,
            amount=format_amount(self.amount, True),
            sender_name=self.sender_name,
            prisoner_name=self.prisoner_name,
            status=self.status
        )

    @property
    def reconcilable(self):
        return not (self.unidentified or self.anomalous)

    @property
    def credited(self):
        return self.credit and self.credit.credited

    @property
    def refunded(self):
        return self.credit and self.credit.refunded

    @property
    def prison(self):
        return self.credit.prison if self.credit else None

    @property
    def prisoner_name(self):
        return self.credit.prisoner_name if self.credit else None

    @property
    def prisoner_dob(self):
        return self.credit.prisoner_dob if self.credit else None

    @property
    def prisoner_number(self):
        return self.credit.prisoner_number if self.credit else None

    @property
    def refundable(self):
        return self.credit and self.prison is None and not self.incomplete_sender_info

    @property
    def creditable(self):
        return self.prison is not None

    @property
    def unidentified(self):
        return (self.prison is None and
                self.incomplete_sender_info and
                self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.BANK_TRANSFER)

    @property
    def anomalous(self):
        return (self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.ADMINISTRATIVE)

    @property
    def status(self):
        if self.unidentified:
            return TRANSACTION_STATUS.UNIDENTIFIED
        elif self.anomalous:
            return TRANSACTION_STATUS.ANOMALOUS
        elif self.creditable:
            return TRANSACTION_STATUS.CREDITABLE
        elif self.refundable:
            return TRANSACTION_STATUS.REFUNDABLE
