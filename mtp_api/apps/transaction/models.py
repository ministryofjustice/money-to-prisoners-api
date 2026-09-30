from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from mtp_common.utils import format_currency

from core.models import TimeStampedModel
from credit.models import Credit
from transaction.constants import TransactionStatus, TransactionCategory, TransactionSource
from transaction.managers import TransactionManager


class Transaction(TimeStampedModel):
    amount = models.BigIntegerField(db_comment='Amount in pence.')
    category = models.CharField(
        max_length=50, choices=TransactionCategory.choices, db_index=True,
        db_comment='credit: money paid in; debit: money paid out.',
    )
    source = models.CharField(
        max_length=50, choices=TransactionSource.choices, db_index=True,
        db_comment='bank_transfer: money sent to a prisoner by bank transfer; '
                   'administrative: anything else, such as card payment settlements and returned payments.',
    )

    processor_type_code = models.CharField(
        max_length=12, blank=True, null=True,
        db_comment='Transaction type code from the bank statement file.',
    )
    sender_sort_code = models.CharField(max_length=50, blank=True, db_comment="Sort code of the sender's account.")
    sender_account_number = models.CharField(
        max_length=50, blank=True,
        db_comment="Account number of the sender's account.",
    )
    sender_name = models.CharField(
        max_length=250, blank=True,
        db_comment="Sender's name, from the description field on the bank statement.",
    )

    # used by building societies to identify the account nr
    sender_roll_number = models.CharField(
        blank=True, max_length=50,
        db_comment='Roll number, for building society accounts that use one to identify the account.',
    )

    # original reference
    reference = models.TextField(
        blank=True,
        db_comment='Reference given by the sender, which should be the prisoner number and date of birth.',
    )
    received_at = models.DateTimeField(
        auto_now=False, db_index=True,
        db_comment='Date on the bank statement, recorded as midday UTC.',
    )

    # 6-digit reference code for reconciliation
    ref_code = models.CharField(
        max_length=12, blank=True, null=True, help_text=_('For reconciliation'),
        db_comment='Reference code given during reconciliation: for bank transfers, numbered from 900001 '
                   'within each day; for a card payment settlement, the code of the card payment batch.',
    )

    incomplete_sender_info = models.BooleanField(
        default=False,
        db_comment="Whether the sender's bank details are missing or incomplete, so the money cannot be "
                   'returned to them.',
    )
    reference_in_sender_field = models.BooleanField(
        default=False,
        db_comment='Whether the prisoner number and date of birth were found in the name field rather than '
                   'the reference.',
    )

    credit = models.OneToOneField(
        Credit, on_delete=models.CASCADE, null=True,
        db_comment='The credit made by this bank transfer; empty for administrative transactions.',
    )

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
        db_table_comment = (
            'Transactions: lines from the statement of the bank account that receives prisoner money, '
            'loaded daily by the Transaction Uploader. Each bank transfer to a prisoner makes one credit.'
        )
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
