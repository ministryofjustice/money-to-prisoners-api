from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from mtp_common.utils import format_currency

from credit.models import Credit
from transaction.constants import TransactionStatus, TransactionCategory, TransactionSource
from transaction.managers import TransactionManager


class Transaction(TimeStampedModel):
    amount = models.BigIntegerField()
    category = models.CharField(max_length=50, choices=TransactionCategory.choices, db_index=True)
    source = models.CharField(max_length=50, choices=TransactionSource.choices, db_index=True)

    processor_type_code = models.CharField(max_length=12, blank=True, null=True)
    sender_sort_code = models.CharField(max_length=50, blank=True)
    sender_account_number = models.CharField(max_length=50, blank=True)
    sender_name = models.CharField(max_length=250, blank=True)

    # used by building societies to identify the account nr
    sender_roll_number = models.CharField(blank=True, max_length=50)

    # original reference
    reference = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now=False, db_index=True)

    # 6-digit reference code for reconciliation
    ref_code = models.CharField(max_length=12, blank=True, null=True,
                                help_text=_('For reconciliation'))

    incomplete_sender_info = models.BooleanField(default=False)
    reference_in_sender_field = models.BooleanField(default=False)

    credit = models.OneToOneField(Credit, on_delete=models.CASCADE, null=True)

    # NB: there are matching boolean fields or properties on the model instance for each
    STATUS_LOOKUP = {
        TransactionStatus.creditable.value: (
            Q(credit__prison__isnull=False) &
            Q(credit__blocked=False)
        ),
        TransactionStatus.refundable.value: (
            Q(incomplete_sender_info=False) & (
                Q(credit__isnull=False) & (
                    Q(credit__prison__isnull=True) |
                    Q(credit__blocked=True)
                )
            )
        ),
        TransactionStatus.anonymous.value: (
            Q(incomplete_sender_info=True) &
            Q(category=TransactionCategory.credit) &
            Q(source=TransactionSource.bank_transfer)
        ),
        TransactionStatus.unidentified.value: (
            Q(incomplete_sender_info=True) &
            (
                Q(credit__isnull=False) & (
                    Q(credit__prison__isnull=True) |
                    Q(credit__blocked=True)
                )
            ) &
            Q(category=TransactionCategory.credit) &
            Q(source=TransactionSource.bank_transfer)
        ),
        TransactionStatus.anomalous.value: (
            Q(category=TransactionCategory.credit) &
            Q(source=TransactionSource.administrative)
        )
    }

    STATUS_LOOKUP[TransactionStatus.reconcilable.value] = (
        ~STATUS_LOOKUP[TransactionStatus.anomalous.value]
    )

    objects = TransactionManager()

    class Meta:
        ordering = ('received_at', 'id',)
        get_latest_by = 'received_at'
        permissions = (
            ('view_dashboard', 'Can view dashboard'),
            ('view_bank_details_transaction', 'Can view bank details of transaction'),
            ('patch_processed_transaction', 'Can patch processed transaction'),
        )

    def __str__(self):
        return 'Transaction {id}, {amount} {sender_name} > {prisoner_name}, {status}'.format(
            id=self.pk,
            amount=format_currency(self.amount, trim_empty_pence=True),
            sender_name=self.sender_name,
            prisoner_name=self.prisoner_name,
            status=self.status
        )

    @property
    def reconcilable(self):
        return not (self.unidentified or self.anomalous)

    @property
    def credited(self):
        return self.credit.credited if self.credit else False

    @property
    def refunded(self):
        return self.credit.refunded if self.credit else False

    @property
    def blocked(self):
        return self.credit.blocked if self.credit else False

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
        return (
            self.credit and (self.prison is None or self.blocked) and
            not self.incomplete_sender_info
        )

    @property
    def creditable(self):
        return self.credit and self.prison is not None and not self.blocked

    @property
    def unidentified(self):
        return (
            self.incomplete_sender_info and
            (self.prison is None or self.blocked) and
            self.category == TransactionCategory.credit.value and
            self.source == TransactionSource.bank_transfer.value
        )

    @property
    def anomalous(self):
        return (self.category == TransactionCategory.credit.value and
                self.source == TransactionSource.administrative.value)

    @property
    def status(self):
        if self.unidentified:
            return TransactionStatus.unidentified.value
        elif self.anomalous:
            return TransactionStatus.anomalous.value
        elif self.creditable:
            return TransactionStatus.creditable.value
        elif self.refundable:
            return TransactionStatus.refundable.value
        elif self.incomplete_sender_info:
            return TransactionStatus.anonymous.value
