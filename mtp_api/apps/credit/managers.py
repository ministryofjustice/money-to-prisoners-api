from django.db import connection, models
from django.db.models import Q
from django.db.transaction import atomic

from credit import InvalidCreditStateException
from credit.constants import CREDIT_STATUS, CREDIT_RESOLUTION, LogAction


class CreditQuerySet(models.QuerySet):
    def credit_pending(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING])

    def credited(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.CREDITED])

    def refunded(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.REFUNDED])

    def refund_pending(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.REFUND_PENDING])

    def failed(self):
        return self.filter(self.model.STATUS_LOOKUP[CREDIT_STATUS.FAILED])

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

    def monitored_by(self, user):
        return self.filter(
            Q(sender_profile__bank_transfer_details__sender_bank_account__monitoring_users=user) |
            Q(sender_profile__debit_card_details__monitoring_users=user) |
            Q(prisoner_profile__monitoring_users=user)
        )


class CreditManager(models.Manager):
    def update_prisons(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE credit_credit
                SET prison_id = pl.prison_id, prisoner_name = pl.prisoner_name
                FROM credit_credit AS c
                LEFT OUTER JOIN prison_prisonerlocation AS pl
                ON c.prisoner_number = pl.prisoner_number
                AND c.prisoner_dob = pl.prisoner_dob AND pl.active IS True
                LEFT OUTER JOIN payment_payment AS p ON p.credit_id=c.id
                WHERE c.owner_id IS NULL AND c.resolution = %s
                AND c.reconciled is False AND credit_credit.id = c.id
                -- don't remove a match from a debit card payment
                AND NOT (pl.prison_id IS NULL AND p.uuid IS NOT NULL)
                """,
                (CREDIT_RESOLUTION.PENDING,)
            )

    @atomic
    def reconcile(self, start_date, end_date, user, **kwargs):
        from credit.models import Log

        update_set = self.get_queryset().filter(
            received_at__gte=start_date,
            received_at__lt=end_date,
            reconciled=False,
            **kwargs
        ).select_for_update()
        Log.objects.credits_reconciled(update_set, user)
        update_set.update(reconciled=True)

    @atomic
    def set_manual(self, queryset, credit_ids, user):
        from credit.models import Log

        to_update = queryset.filter(
            resolution=CREDIT_RESOLUTION.PENDING,
            pk__in=credit_ids
        ).select_for_update()
        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(credit_ids) - set(ids_to_update)

        Log.objects.credits_set_manual(to_update, user)
        to_update.update(resolution=CREDIT_RESOLUTION.MANUAL, owner=user)
        return sorted(conflict_ids)

    @atomic
    def refund(self, transaction_ids, user):
        from credit.models import Credit, Log

        update_set = self.get_queryset().filter(
            Credit.STATUS_LOOKUP['refund_pending'],
            transaction__pk__in=transaction_ids).select_for_update()
        conflict_ids = set(transaction_ids) - {c.transaction.id for c in update_set}
        if conflict_ids:
            raise InvalidCreditStateException(sorted(conflict_ids))

        Log.objects.credits_refunded(update_set, user)
        update_set.update(resolution=CREDIT_RESOLUTION.REFUNDED)

    @atomic
    def review(self, credit_ids, user):
        from credit.models import Log

        to_update = self.get_queryset().filter(
            pk__in=credit_ids
        ).select_for_update()
        Log.objects.credits_reviewed(to_update, user)
        to_update.update(reviewed=True)


# TODO Refactor this as it goes against django good practice
# https://docs.djangoproject.com/en/2.0/topics/db/managers/#don-t-filter-away-any-results-in-this-type-of-manager-subclass  # noqa: E501
class CompletedCreditManager(CreditManager):
    def get_queryset(self):
        return super().get_queryset().exclude(
            resolution__in=(
                CREDIT_RESOLUTION.INITIAL,
                CREDIT_RESOLUTION.FAILED,
            )
        )


class LogManager(models.Manager):
    def _log_action(self, action, credits, by_user=None):
        logs = []
        from credit.models import Log
        for credit in credits:
            logs.append(Log(
                credit=credit,
                action=action,
                user=by_user
            ))
        self.bulk_create(logs)

    def credits_created(self, credits, by_user=None):
        self._log_action(LogAction.created, credits, by_user)

    def credits_credited(self, credits, by_user, credited=True):
        action = LogAction.credited if credited else LogAction.uncredited
        self._log_action(action, credits, by_user)

    def credits_refunded(self, credits, by_user):
        self._log_action(LogAction.refunded, credits, by_user)

    def credits_reconciled(self, credits, by_user):
        self._log_action(LogAction.reconciled, credits, by_user)

    def credits_reviewed(self, credits, by_user):
        self._log_action(LogAction.reviewed, credits, by_user)

    def credits_set_manual(self, credits, by_user):
        self._log_action(LogAction.manual, credits, by_user)

    def credits_failed(self, credits):
        self._log_action(LogAction.failed, credits)

    def get_action_date(self, action):
        log = self.filter(action=action).order_by('-created').first()
        return log and log.created


class CreditingTimeManager(models.Manager):
    @classmethod
    def recalculate_crediting_times(cls):
        """
        Recalculate all crediting times, the time from receipt until a credited status is logged
        NB: crediting does not happen at weekends so an adjustment is needed
        :return: the number of credits with calculated times
        """
        with connection.cursor() as cursor:
            cursor.execute("""
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
            """, (LogAction.credited.value,))
            return cursor.rowcount


class PrivateEstateBatchManager(models.Manager):
    @atomic
    def create_batches(self, start_date, end_date):
        from credit.models import Credit
        from prison.models import Prison

        batch_date = start_date.date()
        credit_list = Credit.objects \
            .filter(
                received_at__gte=start_date,
                received_at__lt=end_date,
                private_estate_batch__isnull=True,  # to ensure that a sent batch doesn't get modified
                prison__private_estate=True,
            ) \
            .filter(
                Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING] |
                Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED]
            )
        for prison in Prison.objects.filter(private_estate=True):
            batch, _ = self.get_or_create(prison=prison, date=batch_date)
            credit_list.filter(prison=prison).update(private_estate_batch=batch)
