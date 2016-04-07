from django.db import models
from django.conf import settings
from model_utils.models import TimeStampedModel

from transaction.models import Transaction
from transaction.utils import format_amount


class Batch(TimeStampedModel):
    label = models.CharField(max_length=30, db_index=True)
    transactions = models.ManyToManyField(Transaction)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ('-created',)
        verbose_name_plural = 'batches'

    def __str__(self):
        return '%s %s' % (self.label, self.created.isoformat())


class Balance(TimeStampedModel):
    closing_balance = models.IntegerField()
    date = models.DateField()

    class Meta:
        ordering = ('-date',)

    def __str__(self):
        return '%s %s' % (self.date.isoformat(), format_amount(self.closing_balance))
