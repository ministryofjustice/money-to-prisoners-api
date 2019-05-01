from django.conf import settings
from django.core.management import BaseCommand
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from mtp_common.tasks import send_email

from credit.models import Credit
from disbursement.models import Disbursement
from mtp_auth.models import PrisonUserMapping
from notification.constants import EMAIL_FREQUENCY, get_notification_period
from notification.models import Event, EmailNotificationPreferences


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--frequency', default=EMAIL_FREQUENCY.WEEKLY,
                            choices=EMAIL_FREQUENCY.values,
                            help='Set which frequency the command is being run for')

    def handle(self, **options):
        frequency = options['frequency']
        preferences = EmailNotificationPreferences.objects.filter(frequency=frequency)
        period_start, period_end = get_notification_period(frequency)
        memo_table = {}

        if frequency == EMAIL_FREQUENCY.DAILY:
            period = _('day')
        elif frequency == EMAIL_FREQUENCY.WEEKLY:
            period = _('week')
        else:
            period = _('month')

        for preference in preferences:
            user = preference.user
            counts = get_notification_counts(
                user, period_start, period_end, memo_table
            )

            if counts['total_notifications'] > 0:
                email_context = {
                    'user': user,
                    'period': period,
                    'period_start': period_start,
                    'total_notifications': counts['total_notifications'],
                    'monitored_transactions': counts['monitored_count'],
                    'transaction_amount_events': counts['transaction_amount_events'],
                    'frequency_events': counts['frequency_events'],
                    'many_senders_receivers_events': counts['many_senders_receivers_events'],
                    'many_prisoners_events': counts['many_prisoners_events'],
                    'notifications_url': '{path}/{date}/'.format(
                        path=settings.NOMS_OPS_NOTIFICATIONS_URL,
                        date=period_start.date().isoformat()
                    ),
                    'settings_url': settings.NOMS_OPS_SETTINGS_URL,
                    'feedback_url': settings.NOMS_OPS_FEEDBACK_URL,
                    'staff_email': True
                }
                send_email(
                    user.email, 'notification/periodic_email.txt',
                    _('You have %s prisoner money intelligence tool notifications')
                    % counts['total_notifications'],
                    context=email_context,
                    html_template='notification/periodic_email.html',
                    anymail_tags=['intelligence-notifications'],
                )


def get_notification_counts(user, period_start, period_end, memo_table=None):
    prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
    key = '.'.join(sorted(list(prisons.values_list('pk', flat=True))))

    if memo_table is not None and key in memo_table:
        counts = memo_table[key].copy()
    else:
        counts = {}

        prison_filter = Q()
        if key:
            prison_filter |= (
                Q(credit_event__credit__prison__in=prisons) |
                Q(disbursement_event__disbursement__prison__in=prisons)
            )

        events = Event.objects.filter(
            prison_filter,
            triggered_at__gte=period_start, triggered_at__lt=period_end
        )
        counts['transaction_amount_events'] = events.filter(
            rule__in=['NWN', 'HA']
        ).count()
        counts['frequency_events'] = (
            events.filter(rule='CSFREQ').values(
                'sender_profile_event__sender_profile'
            ).distinct().count() +
            events.filter(rule='DRFREQ').values(
                'recipient_profile_event__recipient_profile'
            ).distinct().count()
        )
        counts['many_senders_receivers_events'] = (
            events.filter(rule__in=['CSNUM', 'DRNUM']).values(
                'prisoner_profile_event__prisoner_profile'
            ).distinct().count()
        )
        counts['many_prisoners_events'] = (
            events.filter(rule='CPNUM').values(
                'sender_profile_event__sender_profile'
            ).distinct().count() +
            events.filter(rule='DPNUM').values(
                'recipient_profile_event__recipient_profile'
            ).distinct().count()
        )
        counts['total_events'] = (
            counts['transaction_amount_events'] + counts['frequency_events'] +
            counts['many_senders_receivers_events'] + counts['many_prisoners_events']
        )
        if memo_table is not None:
            memo_table[key] = counts.copy()

    monitored_credits = Credit.objects.filter(
        received_at__gte=period_start, received_at__lt=period_end
    ).get_monitored_credits(user)
    monitored_disbursements = Disbursement.objects.filter(
        created__gte=period_start, created__lt=period_end
    ).get_monitored_disbursements(user)
    counts['monitored_count'] = monitored_credits.count() + monitored_disbursements.count()

    counts['total_notifications'] = counts['total_events'] + counts['monitored_count']

    return counts
