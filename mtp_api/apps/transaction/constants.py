from django.db import models
from django.utils.translation import gettext_lazy as _


class TransactionStatus(models.TextChoices):
    # transactions which can be or have been credited
    creditable = 'creditable', _('Creditable')

    # transactions which can be or have been refunded
    refundable = 'refundable', _('Refundable')

    # transactions with incomplete sender info
    anonymous = 'anonymous', _('Anonymous')

    # transactions which can be neither credited nor refunded
    unidentified = 'unidentified', _('Unidentified')

    # transactions of an unknown type
    anomalous = 'anomalous', _('Anomalous')

    # transactions that can be reconciled
    reconcilable = 'reconcilable', _('Reconcilable')


class TransactionCategory(models.TextChoices):
    debit = 'debit', _('Debit')
    credit = 'credit', _('Credit')


class TransactionSource(models.TextChoices):
    bank_transfer = 'bank_transfer', _('Bank transfer')
    administrative = 'administrative', _('Administrative')
