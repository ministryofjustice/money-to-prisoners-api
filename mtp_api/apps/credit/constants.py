from django.db import models
from django.utils.translation import gettext_lazy as _


class CREDIT_RESOLUTION(models.TextChoices):  # noqa: N801
    INITIAL = 'initial', _('Initial')
    PENDING = 'pending', _('Pending')
    MANUAL = 'manual', _('Requires manual processing')
    CREDITED = 'credited', _('Credited')
    REFUNDED = 'refunded', _('Refunded')
    FAILED = 'failed', _('Failed')


class CREDIT_STATUS(models.TextChoices):  # noqa: N801
    CREDIT_PENDING = 'credit_pending', _('Credit pending')
    CREDITED = 'credited', _('Credited')
    REFUNDED = 'refunded', _('Refunded')
    REFUND_PENDING = 'refund_pending', _('Refund pending')
    FAILED = 'failed', _('Failed')


class CREDIT_SOURCE(models.TextChoices):  # noqa: N801
    BANK_TRANSFER = 'bank_transfer', _('Bank transfer')
    ONLINE = 'online', _('Online')
    UNKNOWN = 'unknown', _('Unknown')


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
