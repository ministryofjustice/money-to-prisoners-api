from django.db import models, connection

from .constants import TRANSACTION_STATUS, LOG_ACTIONS


class TransactionQuerySet(models.QuerySet):

    def available(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.AVAILABLE])

    def locked(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.LOCKED])

    def credited(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITED])

    def refunded(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.REFUNDED])

    def refund_pending(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.REFUND_PENDING])

    def locked_by(self, user):
        return self.filter(owner=user)

    def update_prisons(self):
        cursor = connection.cursor()

        cursor.execute(
            'UPDATE transaction_transaction '
            'SET prison_id = pl.prison_id, prisoner_name = pl.prisoner_name '
            'FROM transaction_transaction AS t LEFT OUTER JOIN prison_prisonerlocation AS pl '
            'ON t.prisoner_number = pl.prisoner_number AND t.prisoner_dob = pl.prisoner_dob '
            'WHERE t.owner_id IS NULL AND t.credited is False AND t.refunded is False '
            'AND t.reconciled is False AND transaction_transaction.id = t.id '
        )


class LogManager(models.Manager):

    def transaction_created(self, transaction, by_user=None):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.CREATED,
            user=by_user
        )

    def transaction_locked(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.LOCKED,
            user=by_user
        )

    def transaction_unlocked(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.UNLOCKED,
            user=by_user
        )

    def transaction_credited(self, transaction, by_user, credited=True):
        action = LOG_ACTIONS.CREDITED if credited else LOG_ACTIONS.UNCREDITED
        self.create(
            transaction=transaction,
            action=action,
            user=by_user
        )

    def transaction_refunded(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.REFUNDED,
            user=by_user
        )

    def transaction_reconciled(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.RECONCILED,
            user=by_user
        )

    def transaction_payment_taken(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.PAYMENT_TAKEN,
            user=by_user
        )

    def transaction_payment_failed(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.PAYMENT_FAILED,
            user=by_user
        )
