from django.utils.translation import gettext_lazy as _
from django.db import models

class CREDIT_RESOLUTION(models.TextChoices):
    INITIAL = 'initial', _('Initial')
    PENDING = 'pending', _('Pending')
    MANUAL = 'manual', _('Requires manual processing')
    CREDITED = 'credited', _('Credited')
    REFUNDED = 'refunded', _('Refunded')
    FAILED = 'failed', _('Failed')

class CREDIT_STATUS(models.TextChoices):
    CREDIT_PENDING = 'credit_pending', _('Credit pending')
    CREDITED = 'credited', _('Credited')
    REFUNDED = 'refunded', _('Refunded')
    REFUND_PENDING = 'refund_pending', _('Refund pending')
    FAILED = 'failed', _('Failed')

class CREDIT_SOURCE(models.TextChoices):
    BANK_TRANSFER = 'bank_transfer', _('Bank transfer')
    ONLINE = 'online', _('Online')
    UNKNOWN = 'unknown', _('Unknown')

LOCK_LIMIT = 20

class LOG_ACTIONS(models.TextChoices):
    CREATED = 'created', _('Created')
    LOCKED = 'locked', _('Locked')  # legacy
    UNLOCKED = 'unlocked', _('Unlocked')  # legacy
    CREDITED = 'credited', _('Credited')
    UNCREDITED = 'uncredited', _('Uncredited')  # never happens
    REFUNDED = 'refunded', _('Refunded')
    RECONCILED = 'reconciled', _('Reconciled')
    REVIEWED = 'reviewed', _('Reviewed')
    MANUAL = 'manual', _('Marked for manual processing')
    FAILED = 'failed', _('Failed')
