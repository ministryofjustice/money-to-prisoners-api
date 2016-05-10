from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions which can be or have been credited
    ('CREDITABLE', 'creditable', 'Creditable'),

    # transactions which can be or have been refunded
    ('REFUNDABLE', 'refundable', 'Refundable'),

    # transactions which can be neither credited nor refunded
    ('UNIDENTIFIED', 'unidentified', 'Unidentified'),

    # transactions of an unknown type
    ('ANOMALOUS', 'anomalous', 'Anomalous')
)

TRANSACTION_CATEGORY = Choices(
    ('DEBIT', 'debit', 'Debit'),
    ('CREDIT', 'credit', 'Credit')
)

TRANSACTION_SOURCE = Choices(
    ('BANK_TRANSFER', 'bank_transfer', 'Bank transfer'),
    ('ADMINISTRATIVE', 'administrative', 'Administrative'),
)
