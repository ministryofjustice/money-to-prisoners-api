from django.db import models
from django.utils.translation import gettext_lazy as _


class LOG_ACTIONS(models.TextChoices):
    CREATED = 'created', _('Created')
    EDITED = 'edited', _('Edited')
    REJECTED = 'rejected', _('Rejected')
    CONFIRMED = 'confirmed', _('Confirmed')
    SENT = 'sent', _('Sent')

class DISBURSEMENT_RESOLUTION(models.TextChoices):
    PENDING = 'pending', _('Pending')
    REJECTED = 'rejected', _('Rejected')
    PRECONFIRMED = 'preconfirmed', _('Pre-confirmed')
    CONFIRMED = 'confirmed', _('Confirmed')
    SENT = 'sent', _('Sent')

class DISBURSEMENT_METHOD(models.TextChoices):
    BANK_TRANSFER = 'bank_transfer', _('Bank transfer')
    CHEQUE = 'cheque', _('Cheque')
