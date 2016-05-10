from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.transaction import atomic


class TransactionQuerySet(models.QuerySet):

    @atomic
    def reconcile(self, date, user):
        update_set = self.filter(
            received_at__gte=date,
            received_at__lt=(date + timedelta(days=1))
        ).order_by('id').select_for_update()

        ref_code = settings.REF_CODE_BASE
        for transaction in update_set:
            if transaction.credit and not transaction.credit.reconciled:
                if transaction.reconcilable:
                    transaction.ref_code = ref_code
                    ref_code += 1
                transaction.credit.reconcile(user)
                transaction.save()
