from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentStatus(models.TextChoices):
    # the GOV.UK payment is ongoing
    pending = 'pending', _('Pending')

    # the GOV.UK payment failed or was in error
    failed = 'failed', _('Failed')

    # the GOV.UK payment was successful and has a capture date
    taken = 'taken', _('Taken')

    # the GOV.UK payment didn't pass our security checks so it was cancelled
    rejected = 'rejected', _('Rejected')

    # the GOV.UK payment was capturable but timed out before being captured
    expired = 'expired', _('Expired')
