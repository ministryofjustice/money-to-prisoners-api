from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext_lazy as _
from mtp_common.tasks import send_email

from notification.constants import EMAIL_FREQUENCY, get_notification_period
from notification.models import Event, EmailNotificationPreferences
from security.utils import get_monitored_credits, get_monitored_disbursements


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--frequency', default=EMAIL_FREQUENCY.WEEKLY,
                            choices=EMAIL_FREQUENCY.values,
                            help='Set which frequency the command is being run for')

    def handle(self, **options):
        frequency = options['frequency']
        preferences = EmailNotificationPreferences.objects.filter(frequency=frequency)
        period_start, period_end = get_notification_period(frequency)

        events = Event.objects.filter(
            triggered_at__gte=period_start, triggered_at__lt=period_end
        )
        transaction_amount_events = events.filter(rule__in=['NWN', 'HA']).count()
        frequency_events = (
            events.filter(rule='CSFREQ').values(
                'sender_profile_event__sender_profile'
            ).distinct().count() +
            events.filter(rule='DRFREQ').values(
                'recipient_profile_event__recipient_profile'
            ).distinct().count()
        )
        many_senders_receivers_events = (
            events.filter(rule__in=['CSNUM', 'DRNUM']).values(
                'prisoner_profile_event__prisoner_profile'
            ).distinct().count()
        )
        many_prisoners_events = (
            events.filter(rule='CPNUM').values(
                'sender_profile_event__sender_profile'
            ).distinct().count() +
            events.filter(rule='DPNUM').values(
                'recipient_profile_event__recipient_profile'
            ).distinct().count()
        )
        total_events = (
            transaction_amount_events + frequency_events +
            many_senders_receivers_events + many_prisoners_events
        )
        if frequency == EMAIL_FREQUENCY.DAILY:
            period = _('day')
        elif frequency == EMAIL_FREQUENCY.WEEKLY:
            period = _('week')
        else:
            period = _('month')

        for preference in preferences:
            user = preference.user
            monitored_credits = get_monitored_credits(
                user, received_at__gte=period_start, received_at__lt=period_end
            )
            monitored_disbursements = get_monitored_disbursements(
                user, created__gte=period_start, created__lt=period_end
            )
            monitored_count = monitored_credits.count() + monitored_disbursements.count()
            total_notifications = total_events + monitored_count
            if total_notifications > 0:
                email_context = {
                    'user': user,
                    'period': period,
                    'period_start': period_start,
                    'total_notifications': total_notifications,
                    'monitored_transactions': monitored_count,
                    'transaction_amount_events': transaction_amount_events,
                    'frequency_events': frequency_events,
                    'many_senders_receivers_events': many_senders_receivers_events,
                    'many_prisoners_events': many_prisoners_events,
                    'notifications_url': settings.NOMS_OPS_NOTIFICATIONS_URL,
                    'settings_url': settings.NOMS_OPS_SETTINGS_URL,
                    'feedback_url': settings.NOMS_OPS_FEEDBACK_URL,
                }
                send_email(
                    user.email, 'notification/periodic_email.txt',
                    _('You have %s prisoner money intelligence tool notifications') % total_notifications,
                    context=email_context,
                    html_template='notification/periodic_email.html',
                    anymail_tags=['intelligence-notifications'],
                )
