from django.db import models
from django.utils.translation import gettext_lazy as _


class TRANSACTION_STATUS(models.TextChoices):  # noqa: N801
    # transactions which can be or have been credited
    CREDITABLE = 'creditable', _('Creditable')

    # transactions which can be or have been refunded
    REFUNDABLE = 'refundable', _('Refundable')

    # transactions with incomplete sender info
    ANONYMOUS = 'anonymous', _('Anonymous')

    # transactions which can be neither credited nor refunded
    UNIDENTIFIED = 'unidentified', _('Unidentified')

    # transactions of an unknown type
    ANOMALOUS = 'anomalous', _('Anomalous')

    # transactions that can be reconciled
    RECONCILABLE = 'reconcilable', _('Reconcilable')


class TRANSACTION_CATEGORY(models.TextChoices):  # noqa: N801
    DEBIT = 'debit', _('Debit')
    CREDIT = 'credit', _('Credit')


class TRANSACTION_SOURCE(models.TextChoices):  # noqa: N801
    BANK_TRANSFER = 'bank_transfer', _('Bank transfer')
    ADMINISTRATIVE = 'administrative', _('Administrative')
