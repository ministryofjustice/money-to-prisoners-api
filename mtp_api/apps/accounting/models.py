from django.db import models
from model_utils.models import TimeStampedModel

class Log(TimeStampedModel):
    transaction = models.ForeignKey('transaction.Transaction')
