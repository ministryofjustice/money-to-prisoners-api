from django.db import models
from django.utils.translation import gettext_lazy as _


# NB: only "daily" is currently supported in noms-ops and email-sending management command
class EmailFrequency(models.TextChoices):
    never = 'never', _('Never')
    daily = 'daily', _('Daily')
    weekly = 'weekly', _('Weekly')
    monthly = 'monthly', _('Monthly')
