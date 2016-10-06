import uuid

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from payment.constants import PAYMENT_STATUS


class PaymentManager(models.Manager):
    def abandoned(self, created_before):
        return self.get_queryset().filter(created__lt=created_before, status=PAYMENT_STATUS.PENDING,
                                          credit__resolution=CREDIT_RESOLUTION.INITIAL)


class Payment(TimeStampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(max_length=50, choices=PAYMENT_STATUS, default=PAYMENT_STATUS.PENDING)
    processor_id = models.CharField(max_length=250, null=True, blank=True)
    amount = models.PositiveIntegerField()
    service_charge = models.PositiveIntegerField(default=0)
    recipient_name = models.CharField(max_length=250, null=True, blank=True,
                                      help_text=_('As specified by the sender'))
    email = models.EmailField(null=True, blank=True,
                              help_text=_('Specified by sender for confirmation emails'))
    credit = models.OneToOneField(Credit, on_delete=models.CASCADE)

    objects = PaymentManager()

    class Meta:
        ordering = ('created',)
        get_latest_by = 'created'
        permissions = (
            ('view_payment', 'Can view payment'),
        )

    def __str__(self):
        return str(self.uuid)

    @property
    def prison(self):
        return self.credit.prison

    @property
    def prisoner_name(self):
        return self.credit.prisoner_name

    @property
    def prisoner_dob(self):
        return self.credit.prisoner_dob

    @property
    def prisoner_number(self):
        return self.credit.prisoner_number


@receiver(pre_save, sender=Payment, dispatch_uid='update_credit_for_payment')
def update_credit_for_payment(sender, instance, **kwargs):
    if (instance.status == PAYMENT_STATUS.TAKEN and
            instance.credit.resolution == CREDIT_RESOLUTION.INITIAL):
        instance.credit.resolution = CREDIT_RESOLUTION.PENDING
        instance.credit.received_at = timezone.now()
        instance.credit.save()
