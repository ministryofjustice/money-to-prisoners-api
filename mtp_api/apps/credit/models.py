from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from extended_choices import Choices
from model_utils.models import TimeStampedModel

from prison.models import Prison, PrisonerLocation

CREDIT_RESOLUTION = Choices(
    ('PENDING', 'pending', 'Pending'),
    ('CREDITED', 'credited', 'Credited'),
    ('REFUNDED', 'refunded', 'Refunded')
)


class Credit(TimeStampedModel):
    amount = models.PositiveIntegerField()
    prisoner_number = models.CharField(blank=True, null=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)
    received_at = models.DateTimeField(auto_now=False, null=True)

    prisoner_name = models.CharField(blank=True, null=True, max_length=250)
    prison = models.ForeignKey(Prison, blank=True, null=True, on_delete=models.SET_NULL)

    resolution = models.CharField(max_length=50, choices=CREDIT_RESOLUTION, default=CREDIT_RESOLUTION.PENDING)
    reconciled = models.BooleanField(default=False)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        permissions = (
            ('view_credit', 'Can view credit'),
        )


@receiver(post_save, sender=Credit, dispatch_uid='update_prison_for_credit')
def update_prison_for_credit(sender, instance, created, *args, **kwargs):
    if (created and
            instance.reconciled is False and
            instance.resolution is CREDIT_RESOLUTION.PENDING and
            instance.owner is None):
        try:
            location = PrisonerLocation.objects.get(
                prisoner_number=instance.prisoner_number,
                prisoner_dob=instance.prisoner_dob
            )
            instance.prisoner_name = location.prisoner_name
            instance.prison = location.prison
            instance.save()
        except PrisonerLocation.DoesNotExist:
            pass
