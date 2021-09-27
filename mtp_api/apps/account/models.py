from django.db import models
from model_utils.models import TimeStampedModel
from mtp_common.utils import format_currency


class Balance(TimeStampedModel):
    closing_balance = models.BigIntegerField()
    date = models.DateField()

    class Meta:
        ordering = ('-date',)

    def __str__(self):
        return f'{self.date.isoformat()} {format_currency(self.closing_balance)}'
