from django.utils.translation import gettext_lazy as _
from extended_choices import Choices

CREDIT_RESOLUTION = Choices(
    ('INITIAL', 'initial', _('Initial')),
    ('PENDING', 'pending', _('Pending')),
    ('CREDITED', 'credited', _('Credited')),
    ('REFUNDED', 'refunded', _('Refunded'))
)

CREDIT_STATUS = Choices(
    ('AVAILABLE', 'available', _('Available')),
    ('LOCKED', 'locked', _('Locked')),
    ('CREDITED', 'credited', _('Credited')),
    ('REFUNDED', 'refunded', _('Refunded')),
    ('REFUND_PENDING', 'refund_pending', _('Refund pending')),
)

CREDIT_SOURCE = Choices(
    ('BANK_TRANSFER', 'bank_transfer', _('Bank transfer')),
    ('ONLINE', 'online', _('Online')),
    ('UNKNOWN', 'unknown', _('Unknown')),
)

LOCK_LIMIT = 20

LOG_ACTIONS = Choices(
    ('CREATED', 'created', _('Created')),
    ('LOCKED', 'locked', _('Locked')),
    ('UNLOCKED', 'unlocked', _('Unlocked')),
    ('CREDITED', 'credited', _('Credited')),
    ('UNCREDITED', 'uncredited', _('Uncredited')),
    ('REFUNDED', 'refunded', _('Refunded')),
    ('RECONCILED', 'reconciled', _('Reconciled')),
    ('REVIEWED', 'reviewed', _('Reviewed')),
)
