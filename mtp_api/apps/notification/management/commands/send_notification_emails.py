from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext_lazy as _
from mtp_common.tasks import send_email

from notification.constants import EMAIL_FREQUENCY, get_notification_period
from notification.models import Event, EmailNotificationPreferences
from notification.rules import ENABLED_RULES
from security.models import PrisonerProfile, BankAccount, DebitCardSenderDetails

EMAILS_STARTED_FLAG = 'notifications-started'


class Command(BaseCommand):
    def handle(self, **options):
        frequency = EMAIL_FREQUENCY.DAILY
        period_start, period_end = get_notification_period(frequency)
        events = get_events(period_start, period_end)

        email_context = {
            'period_start': period_start,
            'notifications_url': (
                f'{settings.NOMS_OPS_URL}/security/notifications/#date-{period_start.date().isoformat()}'
            ),
            'sender_url': f'{settings.NOMS_OPS_URL}/security/senders/',
            'prisoner_url': f'{settings.NOMS_OPS_URL}/security/prisoners/',
            'settings_url': f'{settings.NOMS_OPS_URL}/settings/',
            'feedback_url': f'{settings.NOMS_OPS_URL}/feedback/',
            'staff_email': True,
        }

        preferences = EmailNotificationPreferences.objects.filter(frequency=frequency)
        for preference in preferences:
            user = preference.user
            event_group = group_events(events, user)

            has_notifications = event_group['transaction_count']
            is_monitoring = any((
                model.objects.filter(monitoring_users=user).exists()
                for model in (PrisonerProfile, DebitCardSenderDetails, BankAccount)
            ))
            emails_started = user.flags.filter(name=EMAILS_STARTED_FLAG).exists()

            email_context['user'] = user
            email_context['event_group'] = event_group
            if emails_started and has_notifications:
                send_email_with_events(email_context)
            elif not emails_started:
                if has_notifications:
                    send_first_email_with_events(email_context)
                    user.flags.create(name=EMAILS_STARTED_FLAG)
                elif not is_monitoring:
                    send_first_email_not_monitoring(email_context)
                    user.flags.create(name=EMAILS_STARTED_FLAG)


def get_events(period_start, period_end):
    return Event.objects.filter(
        rule__in=ENABLED_RULES,
        triggered_at__gte=period_start, triggered_at__lt=period_end,
    )


def group_events(events, user):
    senders = {}
    prisoners = {}
    for event in events.filter(user=user):
        if hasattr(event, 'sender_profile_event'):
            profile = event.sender_profile_event.sender_profile
            if profile.id in senders:
                details = senders[profile.id]
            else:
                details = make_date_group_profile(
                    profile.id,
                    profile.get_sorted_sender_names()[0]
                )
                senders[profile.id] = details
            if hasattr(event, 'credit_event'):
                details['credit_ids'].add(event.credit_event.credit_id)
            if hasattr(event, 'disbursement_event'):
                details['disbursement_ids'].add(event.disbursement_event.disbursement_id)

        if hasattr(event, 'prisoner_profile_event'):
            profile = event.prisoner_profile_event.prisoner_profile
            if profile.id in prisoners:
                details = prisoners[profile.id]
            else:
                details = make_date_group_profile(
                    profile.id,
                    f'{profile.prisoner_name} ({profile.prisoner_number})'
                )
                prisoners[profile.id] = details
            if hasattr(event, 'credit_event'):
                details['credit_ids'].add(event.credit_event.credit_id)
            if hasattr(event, 'disbursement_event'):
                details['disbursement_ids'].add(event.disbursement_event.disbursement_id)

    senders = sorted(senders.values(), key=lambda sender: sender['description'])
    prisoners = sorted(prisoners.values(), key=lambda prisoner: prisoner['description'])
    transaction_count = 0
    for profile in senders:
        profile.pop('disbursement_ids')
        profile['transaction_count'] = len(profile.pop('credit_ids'))
        transaction_count += profile['transaction_count']
    for profile in prisoners:
        profile['disbursements_only'] = bool(profile['disbursement_ids'] and not profile['credit_ids'])
        profile['transaction_count'] = len(profile.pop('credit_ids')) + len(profile.pop('disbursement_ids'))
        transaction_count += profile['transaction_count']

    return {
        'senders': senders,
        'prisoners': prisoners,
        'transaction_count': transaction_count,
    }


def make_date_group_profile(profile_id, description):
    return {
        'id': profile_id,
        'description': description,
        'credit_ids': set(),
        'disbursement_ids': set(),
    }


def send_email_with_events(email_context):
    send_email(
        email_context['user'].email, 'notification/notifications.txt',
        _('Your new intelligence tool notifications'),
        context=email_context,
        html_template='notification/notifications.html',
        anymail_tags=['intel-notification', 'intel-notification-daily'],
    )


def send_first_email_with_events(email_context):
    send_email(
        email_context['user'].email, 'notification/notifications-first.txt',
        _('New notification feature added to intelligence tool'),
        context=email_context,
        html_template='notification/notifications-first.html',
        anymail_tags=['intel-notification', 'intel-notification-first'],
    )


def send_first_email_not_monitoring(email_context):
    send_email(
        email_context['user'].email, 'notification/not-monitoring.txt',
        _('New helpful ways to get the best from the intelligence tool'),
        context=email_context,
        html_template='notification/not-monitoring.html',
        anymail_tags=['intel-notification', 'intel-notification-not-monitoring'],
    )
