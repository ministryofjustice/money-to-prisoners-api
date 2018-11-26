from django.core.management import BaseCommand
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from mtp_common.tasks import send_email

from notification.constants import EMAIL_FREQUENCY, get_notification_period_start
from notification.models import Event, EmailNotificationPreferences


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('frequency', default=EMAIL_FREQUENCY.DAILY,
                            choices=EMAIL_FREQUENCY.values,
                            help='Set which frequency the command is being run for')

    def handle(self, **options):
        frequency = options['frequency']
        preferences = EmailNotificationPreferences.objects.filter(frequency=frequency)
        events_since = get_notification_period_start(frequency)

        for preference in preferences:
            with atomic():
                user = preference.user
                events = Event.objects.filter(
                    user=user, email_sent=False, created__gte=events_since
                ).order_by('-pk').select_for_update()
                if len(events):
                    self.send_email(user, events)
                    events.update(email_sent=True)

    def send_email(self, user, events):
        email_context = {
            'user': user,
            'events': events[:10]
        }
        send_email(
            user.email, 'notification/new_events.txt',
            _('You have new prisoner money intelligence notifications'),
            context=email_context, html_template='notification/new_events.html',
            anymail_tags=['event-notification'],
        )
