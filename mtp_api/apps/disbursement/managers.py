from django.db import models
from django.db.transaction import atomic

from .constants import LOG_ACTIONS, DISBURSEMENT_RESOLUTION


class DisbursementQuerySet(models.QuerySet):
    def rejected(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.REJECTED)

    def confirmed(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.CONFIRMED)

    def sent(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.SENT)


class DisbursementManager(models.Manager):

    @atomic
    def update_resolution(self, queryset, credit_ids, resolution, user):
        to_update = queryset.filter(
            pk__in=credit_ids
        ).select_for_update()

        from .models import Log
        if resolution == DISBURSEMENT_RESOLUTION.REJECTED:
            Log.objects.disbursements_rejected(to_update, user)
        elif resolution == DISBURSEMENT_RESOLUTION.CONFIRMED:
            Log.objects.disbursements_confirmed(to_update, user)
        elif resolution == DISBURSEMENT_RESOLUTION.SENT:
            Log.objects.disbursements_sent(to_update, user)
        to_update.update(resolution=resolution)


class LogManager(models.Manager):

    def _log_action(self, action, disbursements, by_user=None):
        logs = []
        from .models import Log
        for disbursement in disbursements:
            logs.append(Log(
                disbursement=disbursement,
                action=action,
                user=by_user
            ))
        self.bulk_create(logs)

    def disbursements_created(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.CREATED, disbursements, by_user)

    def disbursements_rejected(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.REJECTED, disbursements, by_user)

    def disbursements_confirmed(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.CONFIRMED, disbursements, by_user)

    def disbursements_sent(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.SENT, disbursements, by_user)
