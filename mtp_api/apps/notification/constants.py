from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


EMAIL_FREQUENCY = Choices(
    ('NEVER', 'never', _('Never')),
    ('DAILY', 'daily', _('Daily')),
    ('WEEKLY', 'weekly', _('Weekly')),
    ('MONTHLY', 'monthly', _('Monthly')),
)
