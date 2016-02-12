import uuid

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from model_utils.models import TimeStampedModel

from transaction.models import Transaction
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE
from transaction.signals import transaction_created, transaction_prisons_need_updating
from .constants import PAYMENT_STATUS


class Payment(TimeStampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(max_length=50, choices=PAYMENT_STATUS, default=PAYMENT_STATUS.PENDING)
    processor_id = models.CharField(max_length=250, null=True)
    amount = models.PositiveIntegerField()
    recipient_name = models.CharField(max_length=250, null=True, blank=True)
    prisoner_number = models.CharField(max_length=250)
    prisoner_dob = models.DateField()
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, null=True)

    class Meta:
        permissions = (
            ('view_payment', 'Can view payment'),
        )

    def __str__(self):
        return str(self.uuid)


@receiver(pre_save, sender=Payment, dispatch_uid='create_transction_for_payment')
def create_transaction_for_payment(sender, instance, **kwargs):
    if instance.status == PAYMENT_STATUS.TAKEN and instance.transaction is None:
        transaction = Transaction()
        transaction.prisoner_number = instance.prisoner_number
        transaction.prisoner_dob = instance.prisoner_dob
        transaction.amount = instance.amount
        transaction.category = TRANSACTION_CATEGORY.CREDIT
        transaction.source = TRANSACTION_SOURCE.ONLINE
        transaction.received_at = instance.modified
        transaction.save()

        instance.transaction = transaction

        transaction_created.send(
            sender=Transaction,
            transaction=transaction,
            by_user=None
        )
        transaction_prisons_need_updating.send(sender=Transaction)
