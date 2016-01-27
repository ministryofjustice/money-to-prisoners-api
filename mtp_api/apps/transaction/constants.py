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
    ('REFUND_PENDING', 'refund_pending', 'Refund Pending')
)


TRANSACTION_CATEGORY = Choices(
    ('DEBIT', 'debit', 'Debit'),
    ('CREDIT', 'credit', 'Credit'),
    ('NON_PAYMENT_CREDIT', 'non_payment_credit', 'Non-payment credit'),
    ('ONLINE_CREDIT', 'online_credit', 'Online credit')
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
