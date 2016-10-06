from django.conf import settings
from django.db import connection
from django.db import models
from django.db.transaction import atomic

from credit.models import Credit
from payment.models import Payment
from .constants import TRANSACTION_STATUS


class TransactionManager(models.Manager):

    @atomic
    def reconcile(self, start_date, end_date, user):
        update_set = self.get_queryset().filter(
            self.model.STATUS_LOOKUP[TRANSACTION_STATUS.RECONCILABLE],
            received_at__gte=start_date,
            received_at__lt=end_date,
            credit__isnull=False,
            credit__reconciled=False
        ).order_by('id').select_for_update()

        ref_codes = []
        ref_code = settings.REF_CODE_BASE
        for transaction in update_set:
            ref_codes.append((transaction.id, ref_code))
            ref_code += 1

        if ref_codes:
            with connection.cursor() as c:
                c.execute('DROP TABLE IF EXISTS refids;')
                c.execute('CREATE TEMP TABLE refids (id integer, ref_code integer)')
                insert_query = 'INSERT INTO refids (id, ref_code) VALUES '
                insert_query += ', '.join(['%s' for _ in ref_codes])
                insert_query += ';'
                c.execute(insert_query, ref_codes)
                c.execute('UPDATE transaction_transaction t SET '
                          'ref_code=r.ref_code FROM refids r WHERE '
                          't.id=r.id;')

        Payment.objects.reconcile(start_date, end_date, user)
        Credit.objects.reconcile(start_date, end_date, user)
