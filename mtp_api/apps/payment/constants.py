from django.utils.translation import gettext_lazy as _
from extended_choices import Choices

PAYMENT_STATUS = Choices(
    ('PENDING', 'pending', _('Pending')),  # the GOV.UK payment is ongoing
    ('FAILED', 'failed', _('Failed')),  # the GOV.UK payment failed or was in error
    ('TAKEN', 'taken', _('Taken')),  # the GOV.UK payment was successful and has a capture date
    ('REJECTED', 'rejected', _('Rejected')),  # the GOV.UK payment didn't pass our security checks so it was cancelled
    ('EXPIRED', 'expired', _('Expired')),  # the GOV.UK payment was capturable but timed out before being captured
)
