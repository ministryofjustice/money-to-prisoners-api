from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


# NB: only DAILY is currently supported in noms-ops and email-sending management command
EMAIL_FREQUENCY = Choices(
    ('NEVER', 'never', _('Never')),
    ('DAILY', 'daily', _('Daily')),
    ('WEEKLY', 'weekly', _('Weekly')),
    ('MONTHLY', 'monthly', _('Monthly')),
)
