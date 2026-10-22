from django.db import models
from mtp_common.utils import format_currency

from core.models import TimeStampedModel


class Balance(TimeStampedModel):
    closing_balance = models.BigIntegerField(db_comment='Balance at the end of the day, in pence.')
    date = models.DateField(db_comment='The day.')

    class Meta:
        db_table_comment = (
            'Account: closing balance of the bank account that receives prisoner money, for each day. '
            'Used by Bank Admin.'
        )
        ordering = ('-date',)

    def __str__(self):
        return f'{self.date.isoformat()} {format_currency(self.closing_balance)}'
