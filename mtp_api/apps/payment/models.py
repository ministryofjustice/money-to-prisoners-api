import re
import uuid

from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from credit.signals import credit_failed
from payment.constants import PAYMENT_STATUS
from payment.managers import PaymentManager
from security.models import Check


class Batch(TimeStampedModel):
    date = models.DateField()
    ref_code = models.CharField(max_length=12, help_text=_('For reconciliation'))
    settlement_transaction = models.OneToOneField(
        'transaction.Transaction', on_delete=models.SET_NULL, blank=True, null=True
    )

    class Meta:
        verbose_name_plural = 'batches'
        ordering = ('date',)
        get_latest_by = 'date'

    def __str__(self):
        return '%s (%s)' % (self.ref_code, self.date)

    @property
    def payment_amount(self):
        return self.payment_set.aggregate(total_amount=models.Sum('amount'))['total_amount']


class BillingAddress(models.Model):
    line1 = models.CharField(max_length=250, blank=True, null=True)
    line2 = models.CharField(max_length=250, blank=True, null=True)
    city = models.CharField(max_length=250, blank=True, null=True)
    country = models.CharField(max_length=250, blank=True, null=True)
    postcode = models.CharField(max_length=250, blank=True, null=True, db_index=True)
    debit_card_sender_details = models.ForeignKey(
        'security.DebitCardSenderDetails', related_name='billing_addresses',
        blank=True, null=True, on_delete=models.SET_NULL
    )

    @property
    def normalised_postcode(self):
        return re.sub(r'[\s-]+', '', self.postcode).upper() if self.postcode else self.postcode

    def __str__(self):
        return ', '.join(filter(None, (self.line1, self.line2, self.city, self.postcode, self.country)))


class Payment(TimeStampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(max_length=50, choices=PAYMENT_STATUS, default=PAYMENT_STATUS.PENDING, db_index=True)
    processor_id = models.CharField(max_length=250, null=True, blank=True, db_index=True)
    worldpay_id = models.CharField(max_length=250, null=True, blank=True, db_index=True)
    amount = models.PositiveIntegerField()
    service_charge = models.PositiveIntegerField(default=0)
    recipient_name = models.CharField(max_length=250, null=True, blank=True,
                                      help_text=_('As specified by the sender'))
    email = models.EmailField(null=True, blank=True,
                              help_text=_('Specified by sender for confirmation emails'),
                              db_index=True)
    credit = models.OneToOneField(Credit, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True)

    cardholder_name = models.CharField(max_length=250, blank=True, null=True, db_index=True)
    card_number_first_digits = models.CharField(max_length=6, blank=True, null=True, db_index=True)
    card_number_last_digits = models.CharField(max_length=4, blank=True, null=True, db_index=True)
    card_expiry_date = models.CharField(max_length=5, blank=True, null=True, db_index=True)
    card_brand = models.CharField(max_length=250, blank=True, null=True)

    ip_address = models.GenericIPAddressField(blank=True, null=True, db_index=True)

    billing_address = models.ForeignKey(
        BillingAddress, on_delete=models.SET_NULL, null=True, blank=True
    )

    objects = PaymentManager()

    class Meta:
        ordering = ('created',)
        get_latest_by = 'created'
        indexes = [
            models.Index(fields=['modified']),
        ]

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

    @property
    def ref_code(self):
        return self.batch.ref_code if self.batch else None

    @property
    def received_at(self):
        return self.credit.received_at


@receiver(pre_save, sender=Payment, dispatch_uid='update_credit_for_payment')
def update_credit_for_payment(instance, **kwargs):
    if (
        instance.status == PAYMENT_STATUS.TAKEN and
        instance.credit.resolution == CREDIT_RESOLUTION.INITIAL
    ):
        if instance.credit.received_at is None:
            instance.credit.received_at = timezone.now()
        instance.credit.resolution = CREDIT_RESOLUTION.PENDING
        instance.credit.save()

    if (
        instance.status in (PAYMENT_STATUS.REJECTED, PAYMENT_STATUS.EXPIRED) and
        instance.credit.resolution == CREDIT_RESOLUTION.INITIAL
    ):
        instance.credit.resolution = CREDIT_RESOLUTION.FAILED
        instance.credit.save()

        credit_failed.send(
            sender=Credit,
            credit=instance.credit,
        )


@receiver(post_save, sender=Payment, dispatch_uid='create_security_check_if_needed_and_attach_profiles')
def create_security_check_if_needed_and_attach_profiles(instance: Payment, **kwargs):
    credit = instance.credit
    if (
        credit.resolution == CREDIT_RESOLUTION.INITIAL
        and instance.status == PAYMENT_STATUS.PENDING
        and credit.has_enough_detail_for_sender_profile()
    ):
        credit.attach_profiles()
        credit.save()
        if not hasattr(credit, 'security_check') and credit.should_check():
            Check.objects.create_for_credit(credit)
