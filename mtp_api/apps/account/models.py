from django.db import models
from model_utils.models import TimeStampedModel

from transaction.utils import format_amount


class Balance(TimeStampedModel):
    closing_balance = models.BigIntegerField()
    date = models.DateField()

    class Meta:
        ordering = ('-date',)

    def __str__(self):
        return '%s %s' % (self.date.isoformat(), format_amount(self.closing_balance))
