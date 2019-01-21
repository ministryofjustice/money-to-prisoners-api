from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


LOG_ACTIONS = Choices(
    ('CREATED', 'created', _('Created')),
    ('EDITED', 'edited', _('Edited')),
    ('REJECTED', 'rejected', _('Rejected')),
    ('CONFIRMED', 'confirmed', _('Confirmed')),
    ('SENT', 'sent', _('Sent')),
    ('CANCELLED', 'cancelled', _('Cancelled')),
)


DISBURSEMENT_RESOLUTION = Choices(
    ('PENDING', 'pending', _('Pending')),
    ('REJECTED', 'rejected', _('Rejected')),
    ('PRECONFIRMED', 'preconfirmed', _('Pre-confirmed')),
    ('CONFIRMED', 'confirmed', _('Confirmed')),
    ('SENT', 'sent', _('Sent')),
    ('CANCELLED', 'cancelled', _('Cancelled')),
)

DISBURSEMENT_METHOD = Choices(
    ('BANK_TRANSFER', 'bank_transfer', _('Bank transfer')),
    ('CHEQUE', 'cheque', _('Cheque')),
)
