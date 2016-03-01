from extended_choices import Choices


TRANSACTION_STATUS = Choices(
    # transactions with owner == None & credited == False & refunded == False
    ('AVAILABLE', 'available', 'Available'),

    # transactions with owner != None & credited == False & refunded == False
    ('LOCKED', 'locked', 'Locked'),

    # transactions with credited == True
    ('CREDITED', 'credited', 'Credited'),

    # transactions with refunded == True
    ('REFUNDED', 'refunded', 'Refunded'),

    # transactions with prisoner_number == None & refunded == False
    ('REFUND_PENDING', 'refund_pending', 'Refund Pending'),

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
    ('ONLINE', 'online', 'Online')
)


# max number of transactions a user can lock at any time
LOCK_LIMIT = 20


LOG_ACTIONS = Choices(
    ('CREATED', 'created', 'Created'),
    ('LOCKED', 'locked', 'Locked'),
    ('UNLOCKED', 'unlocked', 'Unlocked'),
    ('CREDITED', 'credited', 'Credited'),
    ('UNCREDITED', 'uncredited', 'Uncredited'),
    ('REFUNDED', 'refunded', 'Refunded'),
    ('RECONCILED', 'reconciled', 'Reconciled'),
)
