from django.db import models
from django.db.models.functions import Concat
from django.db.transaction import atomic

from . import InvalidDisbursementStateException
from .constants import LOG_ACTIONS, DISBURSEMENT_RESOLUTION


class DisbursementQuerySet(models.QuerySet):
    def rejected(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.REJECTED)

    def preconfirmed(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.PRECONFIRMED)

    def confirmed(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.CONFIRMED)

    def sent(self):
        return self.filter(resolution=DISBURSEMENT_RESOLUTION.SENT)

    def counts_per_day(self):
        return self.extra({'created_date': 'disbursement_disbursement.created::date'}) \
            .values('created_date') \
            .order_by('created_date') \
            .annotate(count_per_day=models.Count('pk'))

    def amounts_per_day(self):
        return self.extra({'created_date': 'disbursement_disbursement.created::date'}) \
            .values('created_date') \
            .order_by('created_date') \
            .annotate(amount_per_day=models.Sum('amount'))


class DisbursementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(
            recipient_name=Concat('recipient_first_name', models.Value(' '), 'recipient_last_name'),
        )

    @atomic
    def update_resolution(self, queryset, disbursement_ids, resolution, user):
        to_update = queryset.filter(
            pk__in=disbursement_ids,
            resolution__in=[self.model.get_permitted_state(resolution), resolution]
        ).select_for_update()

        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(disbursement_ids) - set(ids_to_update)
        if conflict_ids:
            raise InvalidDisbursementStateException(sorted(conflict_ids))

        to_update = to_update.exclude(resolution=resolution)

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

    def disbursements_edited(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.EDITED, disbursements, by_user)

    def disbursements_rejected(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.REJECTED, disbursements, by_user)

    def disbursements_confirmed(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.CONFIRMED, disbursements, by_user)

    def disbursements_sent(self, disbursements, by_user):
        self._log_action(LOG_ACTIONS.SENT, disbursements, by_user)
