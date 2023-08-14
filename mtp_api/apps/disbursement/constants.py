from django.db import models
from django.utils.translation import gettext_lazy as _


class DisbursementResolution(models.TextChoices):
    pending = 'pending', _('Pending')
    rejected = 'rejected', _('Rejected')
    preconfirmed = 'preconfirmed', _('Pre-confirmed')
    confirmed = 'confirmed', _('Confirmed')
    sent = 'sent', _('Sent')


class DisbursementMethod(models.TextChoices):
    bank_transfer = 'bank_transfer', _('Bank transfer')
    cheque = 'cheque', _('Cheque')


class LogAction(models.TextChoices):
    created = 'created', _('Created')
    edited = 'edited', _('Edited')
    rejected = 'rejected', _('Rejected')
    confirmed = 'confirmed', _('Confirmed')
    sent = 'sent', _('Sent')
