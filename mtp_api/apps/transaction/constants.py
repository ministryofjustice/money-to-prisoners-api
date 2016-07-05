from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions which can be or have been credited
    ('CREDITABLE', 'creditable', _('Creditable')),

    # transactions which can be or have been refunded
    ('REFUNDABLE', 'refundable', _('Refundable')),

    # transactions with incomplete sender info
    ('ANONYMOUS', 'anonymous', _('Anonymous')),

    # transactions which can be neither credited nor refunded
    ('UNIDENTIFIED', 'unidentified', _('Unidentified')),

    # transactions of an unknown type
    ('ANOMALOUS', 'anomalous', _('Anomalous')),

    # transactions that can be reconciled
    ('RECONCILABLE', 'reconcilable', _('Reconcilable'))
)

TRANSACTION_CATEGORY = Choices(
    ('DEBIT', 'debit', _('Debit')),
    ('CREDIT', 'credit', _('Credit'))
)

TRANSACTION_SOURCE = Choices(
    ('BANK_TRANSFER', 'bank_transfer', _('Bank transfer')),
    ('ADMINISTRATIVE', 'administrative', _('Administrative')),
)
