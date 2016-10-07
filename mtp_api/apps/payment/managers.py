from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.db.transaction import atomic
from django.utils.timezone import utc

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from .constants import PAYMENT_STATUS


class PaymentManager(models.Manager):

    def abandoned(self, created_before):
        return self.get_queryset().filter(created__lt=created_before, status=PAYMENT_STATUS.PENDING,
                                          credit__resolution=CREDIT_RESOLUTION.INITIAL)

    @atomic
    def reconcile(self, start_date, end_date, user):
        def set_worldpay_cutoff(date):
            return datetime.combine(date - timedelta(days=1), time(23, 0, tzinfo=utc))

        update_set = self.get_queryset().filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=set_worldpay_cutoff(start_date),
            credit__received_at__lt=set_worldpay_cutoff(end_date),
            credit__reconciled=False
        ).select_for_update()

        if update_set.count() > 0:
            from .models import Batch
            try:
                ref_code = int(Batch.objects.latest('created').ref_code) + 1
            except Batch.DoesNotExist:
                ref_code = settings.CARD_REF_CODE_BASE

            new_batch = Batch(
                date=end_date - timedelta(days=1), ref_code=ref_code
            )
            new_batch.save()
            update_set.update(batch=new_batch)

        Credit.objects.reconcile(
            set_worldpay_cutoff(start_date), set_worldpay_cutoff(end_date),
            user, payment__isnull=False
        )
