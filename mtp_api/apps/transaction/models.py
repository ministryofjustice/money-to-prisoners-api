from django.db import models

from model_utils.models import TimeStampedModel

from prison.models import Prison


class Transaction(TimeStampedModel):
    upload_counter = models.PositiveIntegerField()

    prison = models.ForeignKey(Prison, blank=True, null=True)

    prisoner_number = models.CharField(blank=True, max_length=250)
    prisoner_name = models.CharField(blank=True, max_length=250)
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
