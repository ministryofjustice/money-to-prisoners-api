from django.db import connection, models
from django.db.transaction import atomic

from . import InvalidCreditStateException
from .constants import LOG_ACTIONS, CREDIT_STATUS, CREDIT_RESOLUTION, LOCK_LIMIT
from .signals import credit_prisons_need_updating


class CreditQuerySet(models.QuerySet):

    def available(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.AVAILABLE])

    def locked(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.LOCKED])

    def credited(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.CREDITED])

    def refunded(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.REFUNDED])

    def refund_pending(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.REFUND_PENDING])

    def locked_by(self, user):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.LOCKED], owner=user)

    def counts_per_day(self):
        return self.exclude(received_at__isnull=True) \
            .extra({'received_at_date': 'credit_credit.received_at::date'}) \
            .values('received_at_date') \
            .order_by('received_at_date') \
            .annotate(count_per_day=models.Count('pk'))

    def amounts_per_day(self):
        return self.exclude(received_at__isnull=True) \
            .extra({'received_at_date': 'credit_credit.received_at::date'}) \
            .values('received_at_date') \
            .order_by('received_at_date') \
            .annotate(amount_per_day=models.Sum('amount'))


class CreditManager(models.Manager):

    def update_prisons(self):
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE credit_credit "
            "SET prison_id = pl.prison_id, prisoner_name = pl.prisoner_name "
            "FROM credit_credit AS c LEFT OUTER JOIN prison_prisonerlocation AS pl "
            "ON c.prisoner_number = pl.prisoner_number "
            "AND c.prisoner_dob = pl.prisoner_dob AND pl.active is True "
            "LEFT OUTER JOIN payment_payment AS p ON p.credit_id=c.id "
            "WHERE c.owner_id IS NULL AND c.resolution = 'pending' "
            "AND c.reconciled is False AND credit_credit.id = c.id "
            # don't remove a match from a debit card payment
            "AND NOT (pl.prison_id IS NULL AND p.uuid IS NOT NULL) "
        )

    @atomic
    def reconcile(self, start_date, end_date, user, **kwargs):
        update_set = self.get_queryset().filter(
            received_at__gte=start_date,
            received_at__lt=end_date,
            reconciled=False,
            **kwargs
        ).select_for_update()

        from .models import Log
        Log.objects.credits_reconciled(update_set, user)
        update_set.update(reconciled=True)

    @atomic
    def lock(self, queryset, user):
        locked_count = queryset.locked_by(user).count()
        if locked_count < LOCK_LIMIT:
            slice_size = LOCK_LIMIT - locked_count
            available = queryset.available()
            to_lock = available[:slice_size].values_list('id', flat=True)
            locking = queryset.filter(pk__in=to_lock).select_for_update()

            if (available.filter(pk__in=to_lock).count() != len(locking)):
                available_ids = available.filter(pk__in=to_lock).values_list('id', flat=True)
                conflict_ids = set(to_lock) - set(available_ids)
                raise InvalidCreditStateException(sorted(conflict_ids))

            from .models import Log
            Log.objects.credits_locked(locking, user)
            locking.update(owner=user)

    @atomic
    def unlock(self, queryset, credit_ids, user):
        to_update = queryset.locked().filter(pk__in=credit_ids).select_for_update()
        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(credit_ids) - set(ids_to_update)

        if conflict_ids:
            raise InvalidCreditStateException(sorted(conflict_ids))

        from .models import Credit, Log
        Log.objects.credits_unlocked(to_update, user)
        to_update.update(owner=None)
        credit_prisons_need_updating.send(sender=Credit)

    @atomic
    def credit(self, queryset, credit_ids, user):
        to_update = queryset.filter(
            owner=user,
            pk__in=credit_ids
        ).select_for_update()

        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(credit_ids) - set(ids_to_update)

        if conflict_ids:
            raise InvalidCreditStateException(sorted(conflict_ids))

        from .models import Log
        Log.objects.credits_credited(to_update, user)
        to_update.update(resolution=CREDIT_RESOLUTION.CREDITED)

    @atomic
    def uncredit(self, queryset, credit_ids, user):
        to_update = queryset.filter(
            owner=user,
            pk__in=credit_ids
        ).select_for_update()

        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(credit_ids) - set(ids_to_update)

        if conflict_ids:
            raise InvalidCreditStateException(sorted(conflict_ids))

        from .models import Log
        Log.objects.credits_credited(to_update, user, credited=False)
        to_update.update(resolution=CREDIT_RESOLUTION.PENDING)

    @atomic
    def refund(self, transaction_ids, user):
        from .models import Credit
        update_set = self.get_queryset().filter(
            Credit.STATUS_LOOKUP['refund_pending'],
            transaction__pk__in=transaction_ids).select_for_update()
        conflict_ids = set(transaction_ids) - {c.transaction.id for c in update_set}

        if conflict_ids:
            raise InvalidCreditStateException(sorted(conflict_ids))

        from .models import Log
        Log.objects.credits_refunded(update_set, user)
        update_set.update(resolution=CREDIT_RESOLUTION.REFUNDED)

    @atomic
    def review(self, credit_ids, user):
        to_update = self.get_queryset().filter(
            pk__in=credit_ids
        ).select_for_update()

        from .models import Log
        Log.objects.credits_reviewed(to_update, user)
        to_update.update(reviewed=True)


class CompletedCreditManager(CreditManager):

    def get_queryset(self):
        return super().get_queryset().exclude(resolution=CREDIT_RESOLUTION.INITIAL)


class LogManager(models.Manager):

    def _log_action(self, action, credits, by_user=None):
        logs = []
        from .models import Log
        for credit in credits:
            logs.append(Log(
                credit=credit,
                action=action,
                user=by_user
            ))
        self.bulk_create(logs)

    def credits_created(self, credits, by_user=None):
        self._log_action(LOG_ACTIONS.CREATED, credits, by_user)

    def credits_locked(self, credits, by_user):
        self._log_action(LOG_ACTIONS.LOCKED, credits, by_user)

    def credits_unlocked(self, credits, by_user):
        self._log_action(LOG_ACTIONS.UNLOCKED, credits, by_user)

    def credits_credited(self, credits, by_user, credited=True):
        action = LOG_ACTIONS.CREDITED if credited else LOG_ACTIONS.UNCREDITED
        self._log_action(action, credits, by_user)

    def credits_refunded(self, credits, by_user):
        self._log_action(LOG_ACTIONS.REFUNDED, credits, by_user)

    def credits_reconciled(self, credits, by_user):
        self._log_action(LOG_ACTIONS.RECONCILED, credits, by_user)

    def credits_reviewed(self, credits, by_user):
        self._log_action(LOG_ACTIONS.REVIEWED, credits, by_user)


class CreditingTimeManager(models.Manager):
    @classmethod
    def recalculate_crediting_times(cls):
        """
        Recalculate all crediting times, the time from receipt until a credited status is logged
        NB: crediting does not happen at weekends so an adjustment is needed
        :return: the number of credits with calculated times
        """
        with connection.cursor() as cursor:
            cursor.execute('''
                TRUNCATE credit_creditingtime;
                WITH adjustments (day_of_week, adjustment) AS (
                    VALUES (1, INTERVAL '0'), (2, INTERVAL '0'), (3, INTERVAL '0'), (4, INTERVAL '0'),
                        (5, INTERVAL '2 days'), (6, INTERVAL '1 day'), (7, INTERVAL '0')),
                credited_log AS (
                    SELECT credit_id, MAX(created) AS created
                    FROM credit_log
                    WHERE credit_log.action = %s
                    GROUP BY credit_id)
                INSERT INTO credit_creditingtime
                SELECT credited_log.credit_id, credited_log.created - credit_credit.received_at - adjustments.adjustment
                FROM credited_log
                JOIN credit_credit ON credit_credit.id = credited_log.credit_id
                JOIN adjustments ON adjustments.day_of_week = EXTRACT(ISODOW FROM credit_credit.received_at);
            ''', (LOG_ACTIONS.CREDITED,))
            return cursor.rowcount
