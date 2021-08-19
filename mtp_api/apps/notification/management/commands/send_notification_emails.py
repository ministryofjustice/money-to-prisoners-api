from django.conf import settings
from django.core.management import BaseCommand
from django.utils import timezone
from django.utils.dateformat import format as format_date
from mtp_common.tasks import send_email

from core.notify.templates import ApiNotifyTemplates
from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences
from notification.rules import ENABLED_RULE_CODES
from notification.utils import get_notification_period
from security.models import PrisonerProfile, BankAccount, DebitCardSenderDetails

EMAILS_STARTED_FLAG = 'notifications-started'


class Command(BaseCommand):
    def handle(self, **options):
        frequency = EMAIL_FREQUENCY.DAILY
        period_start, period_end = get_notification_period(frequency)
        events = get_events(period_start, period_end)

        base_email_context = {
            'date': format_date(period_start, 'd/m/Y'),
            'notifications_url': (
                f'{settings.NOMS_OPS_URL}/security/notifications/#date-{period_start.date().isoformat()}'
            ),
            'settings_url': f'{settings.NOMS_OPS_URL}/settings/',
            'feedback_url': f'{settings.NOMS_OPS_URL}/feedback/',
            'staff_email': True,
        }

        today = timezone.now().date()
        preferences = EmailNotificationPreferences.objects.filter(frequency=frequency).exclude(last_sent_at=today)
        for preference in preferences:
            user = preference.user
            event_group = summarise_group(group_events(events, user))

            has_notifications = event_group['transaction_count']
            is_monitoring = any((
                model.objects.filter(monitoring_users=user).exists()
                for model in (PrisonerProfile, DebitCardSenderDetails, BankAccount)
            ))
            emails_started = user.flags.filter(name=EMAILS_STARTED_FLAG).exists()

            email_context = dict(
                base_email_context,
                user=user,
                event_group=event_group,
                name=user.get_full_name(),
                count=event_group['transaction_count'],
            )
            email_sent = False
            if emails_started and has_notifications:
                send_email_with_events('api-intel-notification-daily', email_context)
                email_sent = True
            elif not emails_started:
                if has_notifications:
                    send_email_with_events('api-intel-notification-first', email_context)
                    user.flags.create(name=EMAILS_STARTED_FLAG)
                    email_sent = True
                elif not is_monitoring:
                    send_email_with_events('api-intel-notification-not-monitoring', email_context)
                    user.flags.create(name=EMAILS_STARTED_FLAG)
                    email_sent = True
            if email_sent:
                preference.last_sent_at = today
                preference.save()


def get_events(period_start, period_end):
    return Event.objects.filter(
        rule__in=ENABLED_RULE_CODES,
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

    return {
        'senders': senders,
        'prisoners': prisoners,
    }


def make_date_group_profile(profile_id, description):
    return {
        'id': profile_id,
        'description': description,
        'credit_ids': set(),
        'disbursement_ids': set(),
    }


def summarise_group(event_group):
    date_group_transaction_count = 0

    sender_summaries = []
    senders = sorted(
        event_group['senders'].values(),
        key=lambda s: s['description']
    )
    for sender in senders:
        profile_transaction_count = len(sender['credit_ids'])
        date_group_transaction_count += profile_transaction_count
        sender_summaries.append({
            'id': sender['id'],
            'transaction_count': profile_transaction_count,
            'description': sender['description'],
        })

    prisoner_summaries = []
    prisoners = sorted(
        event_group['prisoners'].values(),
        key=lambda p: p['description']
    )
    for prisoner in prisoners:
        disbursements_only = bool(prisoner['disbursement_ids'] and not prisoner['credit_ids'])
        profile_transaction_count = len(prisoner['credit_ids']) + len(prisoner['disbursement_ids'])
        date_group_transaction_count += profile_transaction_count
        prisoner_summaries.append({
            'id': prisoner['id'],
            'transaction_count': profile_transaction_count,
            'description': prisoner['description'],
            'disbursements_only': disbursements_only,
        })

    return {
        'transaction_count': date_group_transaction_count,
        'senders': sender_summaries,
        'prisoners': prisoner_summaries,
    }


def send_email_with_events(template_name, email_context):
    notifications_text = ''
    if email_context['event_group'].get('senders'):
        senders = email_context['event_group']['senders']
        notifications_text += '\n* Payment sources *\n'
        for profile in senders:
            notifications_text += f"{profile['description']} – {profile['transaction_count']} transactions\n"
    if email_context['event_group'].get('prisoners'):
        prisoners = email_context['event_group']['prisoners']
        notifications_text += '\n* Prisoners *\n'
        for profile in prisoners:
            notifications_text += f"{profile['description']} – {profile['transaction_count']} transactions\n"
    email_context['notifications_text'] = notifications_text.strip()

    personalisation = {
        field: email_context[field]
        for field in ApiNotifyTemplates.templates[template_name]['personalisation']
    }
    send_email(
        template_name=template_name,
        to=email_context['user'].email,
        personalisation=personalisation,
        staff_email=True,
    )
