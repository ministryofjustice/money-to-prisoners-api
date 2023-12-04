import datetime
import textwrap
from typing import Sequence

from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from account.models import Balance
from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import Event, CreditEvent, DisbursementEvent, PrisonerProfileEvent, RecipientProfileEvent, SenderProfileEvent
from payment.models import Batch, Payment
from prison.models import Prison, PrisonerLocation
from security.models import (
    RecipientProfile, SenderProfile, PrisonerProfile, SavedSearch
)
from transaction.models import Transaction


class Command(BaseCommand):
    """
    Deletes data which is older than 7 years
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options['verbosity']

        self.print_message = self.stdout.write if verbosity else lambda m: m

        today = timezone.localdate()
        seven_years_ago = today - datetime.timedelta(days=7*365)

        self.print_message(f'\nDeleting Credits older than {seven_years_ago}...')
        credits_to_delete = Credit.objects.filter(created__lt=seven_years_ago)
        for credit in credits_to_delete:
            self.delete_credit(credit)

        self.print_message(f'\nDeleting Disbursments older than {seven_years_ago}...')
        disbursements_to_delete = Disbursement.objects.filter(created__lt=seven_years_ago)
        for disbursement in disbursements_to_delete:
            self.delete_disbursement(disbursement)

        self.print_message(f'\nDeleting Transactions older than {seven_years_ago}...')
        records_deleted = Transaction.objects.filter(received_at__lt=seven_years_ago).delete()
        self.print_message(f'Records deleted: {records_deleted}.')

        self.print_message(f'\nDeleting Payment older than {seven_years_ago}...')
        records_deleted = Payment.objects.filter(modified__lt=seven_years_ago).delete()
        self.print_message(f'Records deleted: {records_deleted}.')

    @transaction.atomic
    def delete_credit(self, credit: Credit):
        self.print_message(f'Deleting Credit {credit}...')

        self.print_message(f'Deleting associated Events...')
        self.delete_events(credit.creditevent_set.all())

        record_deleted = credit.delete()
        self.print_message(f'Records deleted: {record_deleted}.')

        sender_profile = credit.sender_profile
        if sender_profile:
            if not sender_profile.credits.exists():
                self.print_message(f'SenderProfile {sender_profile} has no credits, deleting...')

                self.print_message(f'Deleting associated Events...')
                self.delete_events(sender_profile.senderprofileevent_set.all())

                self.print_message(f"Deleting SenderProfile's SavedSearches '*/senders/{sender_profile.id}/*'...")
                record_deleted = SavedSearch.objects \
                    .filter(site_url__contains=f'/senders/{sender_profile.id}/') \
                    .delete()
                self.print_message(f'Records deleted: {record_deleted}.')

                record_deleted = sender_profile.delete()
                self.print_message(f'Records deleted: {record_deleted}.')
            else:
                SenderProfile.objects \
                    .filter(id=sender_profile.id) \
                    .recalculate_totals()
                self.print_message(f'SenderProfile {sender_profile} updated.')

        self.update_or_delete_prisoner_profile(credit.prisoner_profile)

    @transaction.atomic
    def delete_disbursement(self, disbursement: Disbursement):
        self.print_message(f'Deleting Disbursement {disbursement}...')

        self.print_message(f'Deleting associated Events...')
        self.delete_events(disbursement.disbursementevent_set.all())

        record_deleted = disbursement.delete()
        self.print_message(f'Records deleted: {record_deleted}.')

        recipient_profile = disbursement.recipient_profile
        if recipient_profile:
            if not recipient_profile.disbursements.exists():
                self.print_message(f'RecipientProfile {recipient_profile} has no disbursements, deleting...')

                self.print_message(f'Deleting associated Events...')
                self.delete_events(recipient_profile.recipientprofileevent_set.all())

                for recipient_details in recipient_profile.bank_transfer_details.all():
                    bank_account = recipient_details.recipient_bank_account
                    # NOTE: Checking only senders because we reached this point via the recipient
                    #       BankTransferRecipientDetails will be cascade-deleted anyway when the RecipientProfile
                    #       will be deleted, so no point in checking if bank_account.recipients is empty.
                    if not bank_account.senders.exists():
                        self.print_message(f'BankAccount {bank_account} has no senders, deleting...')
                        record_deleted = bank_account.delete()
                        self.print_message(f'Records deleted: {record_deleted}.')

                record_deleted = recipient_profile.delete()
                self.print_message(f'Records deleted: {record_deleted}.')
            else:
                RecipientProfile.objects \
                    .filter(id=recipient_profile.id) \
                    .recalculate_totals()
                self.print_message(f'RecipientProfile {recipient_profile} updated.')

        self.update_or_delete_prisoner_profile(disbursement.prisoner_profile)

    def update_or_delete_prisoner_profile(self, prisoner_profile: PrisonerProfile | None):
        if prisoner_profile:
            if not prisoner_profile.credits.exists() and not prisoner_profile.disbursements.exists():
                self.print_message(f'PrisonerProfile {prisoner_profile} has no credits nor disbursements, deleting...')

                self.print_message(f'Deleting associated Events...')
                self.delete_events(prisoner_profile.prisonerprofileevent_set.all())

                self.print_message(f"Deleting PrisoneProfile's SavedSearches '*/prisoners/{prisoner_profile.id}/*'...")
                record_deleted = SavedSearch.objects \
                    .filter(site_url__contains=f'/prisoners/{prisoner_profile.id}/') \
                    .delete()
                self.print_message(f'Records deleted: {record_deleted}.')

                record_deleted = prisoner_profile.delete()
                self.print_message(f'Records deleted: {record_deleted}.')
            else:
                PrisonerProfile.objects \
                            .filter(id=prisoner_profile.id) \
                            .recalculate_totals()
                self.print_message(f'PrisonerProfile {prisoner_profile} updated.')

    def delete_events(self, thing_events: Sequence[CreditEvent | DisbursementEvent | PrisonerProfileEvent | RecipientProfileEvent |SenderProfileEvent]):
        for thing_event in thing_events:
            event = thing_event.event
            self.print_message(f'Deleting Event {event}...')
            record_deleted = event.delete()
            self.print_message(f'Records deleted: {record_deleted}.')
