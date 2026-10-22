import re
import uuid

from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from credit.constants import CreditResolution
from credit.models import Credit
from core.models import TimeStampedModel
from credit.signals import credit_failed
from payment.constants import PaymentStatus
from payment.managers import PaymentManager
from security.models import Check


class Batch(TimeStampedModel):
    date = models.DateField(db_comment='Day on which the card payments in this batch were received.')
    ref_code = models.CharField(
        max_length=12, help_text=_('For reconciliation'),
        db_comment='Reference code given to the batch during reconciliation, counting up from 800001.',
    )
    settlement_transaction = models.OneToOneField(
        'transaction.Transaction', on_delete=models.SET_NULL, blank=True, null=True,
        db_comment='The line on the bank statement where the card payment provider paid in this batch.',
    )

    class Meta:
        db_table_comment = (
            "Payments: one day's debit card payments, grouped during reconciliation so that they can be matched "
            'to the single amount the card payment provider pays into the bank.'
        )
        verbose_name_plural = 'batches'
        ordering = ('date',)
        get_latest_by = 'date'

    def __str__(self):
        return '%s (%s)' % (self.ref_code, self.date)

    @property
    def payment_amount(self):
        return self.payment_set.aggregate(total_amount=models.Sum('amount'))['total_amount']


class BillingAddress(models.Model):
    line1 = models.CharField(max_length=250, blank=True, null=True, db_comment='First line of the address.')
    line2 = models.CharField(max_length=250, blank=True, null=True, db_comment='Second line of the address.')
    city = models.CharField(max_length=250, blank=True, null=True, db_comment='Town or city.')
    country = models.CharField(max_length=250, blank=True, null=True, db_comment='Country.')
    postcode = models.CharField(max_length=250, blank=True, null=True, db_comment='Postcode.')
    debit_card_sender_details = models.ForeignKey(
        'security.DebitCardSenderDetails', related_name='billing_addresses',
        blank=True, null=True, on_delete=models.SET_NULL,
        db_comment='The card details, in a sender profile, that this address was given with.',
    )

    class Meta:
        db_table_comment = 'Payments: billing addresses that senders gave with debit card payments.'

    @property
    def normalised_postcode(self):
        return re.sub(r'[\s-]+', '', self.postcode).upper() if self.postcode else self.postcode

    def __str__(self):
        return ', '.join(filter(None, (self.line1, self.line2, self.city, self.postcode, self.country)))


class Payment(TimeStampedModel):
    uuid = models.UUIDField(
        default=uuid.uuid4, primary_key=True, editable=False,
        db_comment='Unique ID for the payment, created by Prisoner Money.',
    )
    status = models.CharField(
        max_length=50, choices=PaymentStatus.choices, default=PaymentStatus.pending.value, db_index=True,
        db_comment='pending: in progress; failed: failed or in error; taken: successful; '
                   'rejected: cancelled because it did not pass checks; expired: not taken in time.',
    )
    processor_id = models.CharField(
        max_length=250, null=True, blank=True, db_index=True,
        db_comment='ID of the payment in GOV.UK Pay.',
    )
    worldpay_id = models.CharField(
        max_length=250, null=True, blank=True, db_index=True,
        db_comment='Order code from the card payment provider (Worldpay), as reported by GOV.UK Pay.',
    )
    amount = models.PositiveIntegerField(db_comment='Amount for the prisoner, in pence.')
    service_charge = models.PositiveIntegerField(
        default=0,
        db_comment='Charge paid by the sender on top of the amount, in pence. Zero when no charge applies.',
    )
    recipient_name = models.CharField(
        max_length=250, null=True, blank=True, help_text=_('As specified by the sender'),
        db_comment="Prisoner's name as entered by the sender.",
    )
    email = models.EmailField(
        null=True, blank=True, help_text=_('Specified by sender for confirmation emails'),
        db_comment="Sender's email address, used for confirmation emails.",
    )
    credit = models.OneToOneField(Credit, on_delete=models.CASCADE, db_comment='The credit this payment makes.')
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True, blank=True,
        db_comment="The day's batch this payment was reconciled in; empty until reconciled.",
    )

    cardholder_name = models.CharField(
        max_length=250, blank=True, null=True,
        db_comment='Name on the card, as entered by the sender.',
    )
    card_number_first_digits = models.CharField(
        max_length=6, blank=True, null=True,
        db_comment='First 6 digits of the card number. The full number is never stored.',
    )
    card_number_last_digits = models.CharField(
        max_length=4, blank=True, null=True,
        db_comment='Last 4 digits of the card number.',
    )
    card_expiry_date = models.CharField(max_length=5, blank=True, null=True, db_comment='Card expiry date, as MM/YY.')
    card_brand = models.CharField(max_length=250, blank=True, null=True, db_comment='Card brand, such as Visa.')

    ip_address = models.GenericIPAddressField(
        blank=True, null=True, db_index=True,
        db_comment='IP address the sender made the payment from.',
    )

    billing_address = models.ForeignKey(
        BillingAddress, on_delete=models.SET_NULL, null=True, blank=True,
        db_comment='Billing address given by the sender.',
    )

    objects = PaymentManager()

    class Meta:
        db_table_comment = (
            'Payments: debit card payments made through Send Money and GOV.UK Pay. Each makes one credit.'
        )
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
        instance.status == PaymentStatus.taken.value and
        instance.credit.resolution == CreditResolution.initial.value
    ):
        if instance.credit.received_at is None:
            instance.credit.received_at = timezone.now()
        instance.credit.resolution = CreditResolution.pending.value
        instance.credit.save()

    if (
        instance.status in (PaymentStatus.rejected.value, PaymentStatus.expired.value) and
        instance.credit.resolution == CreditResolution.initial.value
    ):
        instance.credit.resolution = CreditResolution.failed.value
        instance.credit.save()

        credit_failed.send(
            sender=Credit,
            credit=instance.credit,
        )


@receiver(post_save, sender=Payment, dispatch_uid='create_security_check_if_needed_and_attach_profiles')
def create_security_check_if_needed_and_attach_profiles(instance: Payment, **kwargs):
    credit = instance.credit
    if (
        credit.resolution == CreditResolution.initial.value
        and instance.status == PaymentStatus.pending.value
        and credit.has_enough_detail_for_sender_profile()
    ):
        credit.attach_profiles()
        credit.save()
        if not hasattr(credit, 'security_check') and credit.should_check():
            Check.objects.create_for_credit(credit)
