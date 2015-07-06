from django.db import models
from django.db.models import Q

from model_utils.models import TimeStampedModel

from prison.models import Prison
from transaction.constants import TRANSACTION_STATUS


class TransactionQuerySet(models.QuerySet):

    def available(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.AVAILABLE])

    def pending(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.PENDING])

    def credited(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITED])

    def locked_by(self, user):
        return self.filter(owner=user)


class Transaction(TimeStampedModel):
    upload_counter = models.PositiveIntegerField()

    prison = models.ForeignKey(Prison, blank=True, null=True)

    prisoner_number = models.CharField(blank=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)

    amount = models.PositiveIntegerField()
    sender_bank_reference = models.CharField(
        blank=True, max_length=250
    )
    sender_customer_reference = models.CharField(
        blank=True, max_length=250
    )
    reference = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now=False)


    owner = models.ForeignKey('auth.User', null=True, blank=True)
    credited = models.BooleanField(default=False)


    STATUS_LOOKUP = {
        TRANSACTION_STATUS.PENDING:   {'owner__isnull': False, 'credited': False},
        TRANSACTION_STATUS.AVAILABLE: {'owner__isnull': True, 'credited': False},
        TRANSACTION_STATUS.CREDITED:  {'owner__isnull': False, 'credited': True}
    }

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ('received_at',)
