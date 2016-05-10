from extended_choices import Choices

CREDIT_RESOLUTION = Choices(
    ('INITIAL', 'initial', 'Initial'),
    ('PENDING', 'pending', 'Pending'),
    ('CREDITED', 'credited', 'Credited'),
    ('REFUNDED', 'refunded', 'Refunded')
)

CREDIT_STATUS = Choices(
    ('AVAILABLE', 'available', 'Available'),
    ('LOCKED', 'locked', 'Locked'),
    ('CREDITED', 'credited', 'Credited'),
    ('REFUNDED', 'refunded', 'Refunded'),
    ('REFUND_PENDING', 'refund_pending', 'Refund Pending'),
)

CREDIT_SOURCE = Choices(
    ('BANK_TRANSFER', 'bank_transfer', 'Bank transfer'),
    ('ONLINE', 'online', 'Online'),
    ('UNKNOWN', 'unknown', 'Unknown'),
)

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
