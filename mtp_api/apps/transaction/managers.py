from django.conf import settings
from django.db import connection
from django.db import models
from django.db.transaction import atomic

from credit.models import Credit
from transaction.constants import TransactionStatus


class TransactionManager(models.Manager):
    @atomic
    def reconcile(self, start_date, end_date, user):
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE transaction_transaction t '
                'SET ref_code=b.ref_code '
                'FROM payment_batch b '
                'WHERE t.id=b.settlement_transaction_id AND '
                'received_at >= %s and received_at < %s',
                [start_date, end_date]
            )

        update_set = self.get_queryset().filter(
            self.model.STATUS_LOOKUP[TransactionStatus.reconcilable.value],
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
            with connection.cursor() as cursor:
                cursor.execute('DROP TABLE IF EXISTS refids;')
                cursor.execute('CREATE TEMP TABLE refids (id integer, ref_code integer);')
                insert_query = 'INSERT INTO refids (id, ref_code) VALUES '
                insert_query += ', '.join('%s' for _ in ref_codes)
                insert_query += ';'
                cursor.execute(insert_query, ref_codes)
                cursor.execute(
                    'UPDATE transaction_transaction t '
                    'SET ref_code = r.ref_code FROM refids r '
                    'WHERE t.id = r.id;'
                )

        Credit.objects.reconcile(start_date, end_date, user, transaction__isnull=False)
