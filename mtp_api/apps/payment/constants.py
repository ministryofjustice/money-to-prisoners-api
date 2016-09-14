from django.utils.translation import gettext_lazy as _
from extended_choices import Choices

PAYMENT_STATUS = Choices(
    ('PENDING', 'pending', _('Pending')),
    ('FAILED', 'failed', _('Failed')),
    ('TAKEN', 'taken', _('Taken'))
)
