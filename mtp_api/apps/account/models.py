from django.db import models
from django.conf import settings
from model_utils.models import TimeStampedModel

from transaction.models import Transaction


class Batch(TimeStampedModel):
    label = models.CharField(max_length=30, db_index=True)
    transactions = models.ManyToManyField(Transaction)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name_plural = 'batches'

    def __str__(self):
        return '%s %s' % (self.label, self.created)


class Balance(TimeStampedModel):
    closing_balance = models.IntegerField()
    date = models.DateField()

    def __str__(self):
        return '%s %s' % (self.date.isoformat(), self.closing_balance)
