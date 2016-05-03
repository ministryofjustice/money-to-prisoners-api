from extended_choices import Choices

LOG_ACTIONS = Choices(
    ('CREATED', 'created', 'Created'),
    ('LOCKED', 'locked', 'Locked'),
    ('UNLOCKED', 'unlocked', 'Unlocked'),
    ('CREDITED', 'credited', 'Credited'),
    ('UNCREDITED', 'uncredited', 'Uncredited'),
    ('REFUNDED', 'refunded', 'Refunded'),
    ('RECONCILED', 'reconciled', 'Reconciled'),
)
