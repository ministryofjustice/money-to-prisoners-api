from django.db import models
from model_utils.models import TimeStampedModel

from transaction.models import Transaction


class FileType(models.Model):
    name = models.CharField(max_length=15, primary_key=True)
    description = models.CharField(max_length=255, null=True)

    def __str__(self):
        return self.description


class File(TimeStampedModel):
    file_type = models.ForeignKey(FileType)
    transactions = models.ManyToManyField(Transaction)

    def __str__(self):
        return '%s %s' % (self.file_type, self.created)


class Balance(TimeStampedModel):
    opening_balance = models.IntegerField()
    closing_balance = models.IntegerField()
    file = models.OneToOneField(File)
