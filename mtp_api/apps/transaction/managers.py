from django.db import models

from .constants import TRANSACTION_STATUS, LOG_ACTIONS


class TransactionQuerySet(models.QuerySet):

    def available(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.AVAILABLE])

    def pending(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.PENDING])

    def credited(self):
        return self.filter(**self.model.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITED])

    def locked_by(self, user):
        return self.filter(owner=user)


class LogManager(models.Manager):

    def transaction_created(self, transaction, by_user=None):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.CREATED,
            user=by_user
        )

    def transaction_taken(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.TAKEN,
            user=by_user
        )

    def transaction_released(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.RELEASED,
            user=by_user
        )

    def transaction_credited(self, transaction, by_user):
        self.create(
            transaction=transaction,
            action=LOG_ACTIONS.CREDITED,
            user=by_user
        )
