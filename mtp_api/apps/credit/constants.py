from django.db import models
from django.utils.translation import gettext_lazy as _


class CreditResolution(models.TextChoices):
    initial = 'initial', _('Initial')
    pending = 'pending', _('Pending')
    manual = 'manual', _('Requires manual processing')
    credited = 'credited', _('Credited')
    refunded = 'refunded', _('Refunded')
    failed = 'failed', _('Failed')


class CreditStatus(models.TextChoices):
    credit_pending = 'credit_pending', _('Credit pending')
    credited = 'credited', _('Credited')
    refunded = 'refunded', _('Refunded')
    refund_pending = 'refund_pending', _('Refund pending')
    failed = 'failed', _('Failed')


class CreditSource(models.TextChoices):
    bank_transfer = 'bank_transfer', _('Bank transfer')
    online = 'online', _('Online')
    unknown = 'unknown', _('Unknown')


class LogAction(models.TextChoices):
    created = 'created', _('Created')
    locked = 'locked', _('Locked')  # legacy
    unlocked = 'unlocked', _('Unlocked')  # legacy
    credited = 'credited', _('Credited')
    uncredited = 'uncredited', _('Uncredited')  # never happens
    refunded = 'refunded', _('Refunded')
    reconciled = 'reconciled', _('Reconciled')
    reviewed = 'reviewed', _('Reviewed')
    manual = 'manual', _('Marked for manual processing')
    failed = 'failed', _('Failed')
