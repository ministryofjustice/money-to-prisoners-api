from django.conf import settings
from django.db import models
from django.db.transaction import atomic

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from payment.constants import PaymentStatus


class PaymentManager(models.Manager):
    def abandoned(self, created_before):
        return self.get_queryset().filter(
            created__lt=created_before,
            status=PaymentStatus.failed,
            credit__resolution=CREDIT_RESOLUTION.INITIAL,
        )

    @atomic
    def reconcile(self, start_date, end_date, user):
        from payment.models import Batch

        update_set = self.get_queryset().filter(
            status=PaymentStatus.taken,
            credit__received_at__gte=start_date,
            credit__received_at__lt=end_date,
            credit__reconciled=False,
        ).select_for_update()

        # use `len` as `select` is needed to acquire lock
        if len(update_set):
            max_ref_code = Batch.objects.all().aggregate(models.Max('ref_code'))['ref_code__max']
            if max_ref_code:
                ref_code = int(max_ref_code) + 1
            else:
                ref_code = settings.CARD_REF_CODE_BASE

            new_batch = Batch(
                date=start_date.date(), ref_code=ref_code
            )
            new_batch.save()
            update_set.update(batch=new_batch)

        Credit.objects.reconcile(start_date, end_date, user, payment__isnull=False)
