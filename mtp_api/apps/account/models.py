from django.db import models
from model_utils.models import TimeStampedModel

from transaction.models import Transaction


class Batch(TimeStampedModel):
    label = models.CharField(max_length=30, db_index=True)
    transactions = models.ManyToManyField(Transaction)

    def __str__(self):
        return '%s %s' % (self.label, self.created)


class Balance(TimeStampedModel):
    opening_balance = models.IntegerField()
    closing_balance = models.IntegerField()
    batch = models.OneToOneField(Batch)
