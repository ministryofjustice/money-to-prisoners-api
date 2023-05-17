from django.db import models
from django.utils.translation import gettext_lazy as _


# NB: only DAILY is currently supported in noms-ops and email-sending management command
class EMAIL_FREQUENCY(models.TextChoices):  # noqa: N801
    NEVER = 'never', _('Never')
    DAILY = 'daily', _('Daily')
    WEEKLY = 'weekly', _('Weekly')
    MONTHLY = 'monthly', _('Monthly')
