from django.db import models

from .constants import LOG_ACTIONS


class LogManager(models.Manager):

    def credit_created(self, credit, by_user=None):
        self.create(
            credit=credit,
            action=LOG_ACTIONS.CREATED,
            user=by_user
        )

    def credit_locked(self, credit, by_user):
        self.create(
            credit=credit,
            action=LOG_ACTIONS.LOCKED,
            user=by_user
        )

    def credit_unlocked(self, credit, by_user):
        self.create(
            credit=credit,
            action=LOG_ACTIONS.UNLOCKED,
            user=by_user
        )

    def credit_credited(self, credit, by_user, credited=True):
        action = LOG_ACTIONS.CREDITED if credited else LOG_ACTIONS.UNCREDITED
        self.create(
            credit=credit,
            action=action,
            user=by_user
        )

    def credit_refunded(self, credit, by_user):
        self.create(
            credit=credit,
            action=LOG_ACTIONS.REFUNDED,
            user=by_user
        )

    def credit_reconciled(self, credit, by_user):
        self.create(
            credit=credit,
            action=LOG_ACTIONS.RECONCILED,
            user=by_user
        )
