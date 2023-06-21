from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Cast, Concat
from django.db.transaction import atomic

from disbursement import InvalidDisbursementStateException
from disbursement.constants import DisbursementResolution, LogAction


class DisbursementQuerySet(models.QuerySet):
    def rejected(self):
        return self.filter(resolution=DisbursementResolution.rejected)

    def preconfirmed(self):
        return self.filter(resolution=DisbursementResolution.preconfirmed)

    def confirmed(self):
        return self.filter(resolution=DisbursementResolution.confirmed)

    def sent(self):
        return self.filter(resolution=DisbursementResolution.sent)

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

    def monitored_by(self, user):
        return self.filter(
            Q(recipient_profile__bank_transfer_details__recipient_bank_account__monitoring_users=user) |
            Q(prisoner_profile__monitoring_users=user)
        )


class DisbursementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(
            recipient_name=Concat('recipient_first_name', models.Value(' '), 'recipient_last_name'),
        )

    @atomic
    def update_resolution(self, queryset, disbursement_ids, resolution, user):
        from disbursement.models import Log

        to_update = queryset.filter(
            pk__in=disbursement_ids,
            resolution__in=[self.model.get_permitted_state(resolution), resolution]
        ).select_for_update()

        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(disbursement_ids) - set(ids_to_update)
        if conflict_ids:
            raise InvalidDisbursementStateException(sorted(conflict_ids))
        to_update = to_update.exclude(resolution=resolution)

        if resolution == DisbursementResolution.rejected.value:
            Log.objects.disbursements_rejected(to_update, user)
        elif resolution == DisbursementResolution.confirmed.value:
            Log.objects.disbursements_confirmed(to_update, user)
        elif resolution == DisbursementResolution.sent.value:
            Log.objects.disbursements_sent(to_update, user)

        if resolution == DisbursementResolution.confirmed.value:
            to_update.update(
                resolution=resolution,
                invoice_number=Concat(
                    models.Value('PMD'),
                    Cast(
                        models.F('id') + settings.INVOICE_NUMBER_BASE,
                        output_field=models.CharField()
                    )
                )
            )
        else:
            to_update.update(resolution=resolution)


class LogManager(models.Manager):
    def _log_action(self, action, disbursements, by_user=None):
        from disbursement.models import Log

        logs = []
        for disbursement in disbursements:
            logs.append(Log(
                disbursement=disbursement,
                action=action,
                user=by_user
            ))
        self.bulk_create(logs)

    def disbursements_created(self, disbursements, by_user):
        self._log_action(LogAction.created, disbursements, by_user)

    def disbursements_edited(self, disbursements, by_user):
        self._log_action(LogAction.edited, disbursements, by_user)

    def disbursements_rejected(self, disbursements, by_user):
        self._log_action(LogAction.rejected, disbursements, by_user)

    def disbursements_confirmed(self, disbursements, by_user):
        self._log_action(LogAction.confirmed, disbursements, by_user)

    def disbursements_sent(self, disbursements, by_user):
        self._log_action(LogAction.sent, disbursements, by_user)

    def get_action_date(self, action):
        log = self.filter(action=action).order_by('-created').first()
        return log and log.created
