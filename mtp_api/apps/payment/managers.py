from django.conf import settings
from django.db import models
from django.db.transaction import atomic

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from .constants import PAYMENT_STATUS


class PaymentManager(models.Manager):

    def abandoned(self, created_before):
        return self.get_queryset().filter(created__lt=created_before, status=PAYMENT_STATUS.PENDING,
                                          credit__resolution=CREDIT_RESOLUTION.INITIAL)

    @atomic
    def reconcile(self, start_date, end_date, user):
        update_set = self.get_queryset().filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=start_date,
            credit__received_at__lt=end_date,
            credit__reconciled=False
        ).select_for_update()

        if update_set.count() > 0:
            from .models import Batch
            try:
                ref_code = int(Batch.objects.latest('created').ref_code) + 1
            except Batch.DoesNotExist:
                ref_code = settings.CARD_REF_CODE_BASE

            new_batch = Batch(
                date=end_date.date(), ref_code=ref_code
            )
            new_batch.save()
            update_set.update(batch=new_batch)

        Credit.objects.reconcile(start_date, end_date, user, payment__isnull=False)
