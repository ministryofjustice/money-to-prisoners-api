from django.db import models
from django.utils.translation import gettext_lazy as _


class CheckStatus(models.TextChoices):
    pending = 'pending', _('Pending')
    accepted = 'accepted', _('Accepted')
    rejected = 'rejected', _('Rejected')
