import datetime
import textwrap
from typing import Sequence

from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.utils import beginning_of_day, date_argument
from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import CreditEvent, DisbursementEvent, PrisonerProfileEvent, \
    RecipientProfileEvent, SenderProfileEvent
from payment.models import BillingAddress, Payment
from security.models import (
    BankAccount, RecipientProfile, SenderProfile, PrisonerProfile, SavedSearch
)
from transaction.models import Transaction
from user_event_log.models import UserEvent


class Command(BaseCommand):
    """
    Deletes data which is older than 7 years
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--before',
            help="Delete data before this date (exclusive). Defaults to 7 years ago. Can't be later than 7 years ago.",
        )

    @classmethod
    def get_cutoff_date(cls, **options):
        today = beginning_of_day(timezone.localdate())
        seven_years_ago = today - datetime.timedelta(days=7*365)

        before = date_argument(options['before'])
        if not before:
            return seven_years_ago
        elif before > seven_years_ago:
            raise CommandError('"--before" must be older than 7 years ago')

        return before

    def print_message(self, message, depth=0):
        self.write('\t' * depth + message)

    def handle(self, *args, **options):
        verbosity = options['verbosity']

        self.write = self.stdout.write if verbosity else lambda m: m

        cutoff_date = self.get_cutoff_date(**options)

        self.print_message(f'\nDeleting Credits older than {cutoff_date}...')
        credits_to_delete = Credit.objects.filter(created__lt=cutoff_date)
        for credit in credits_to_delete:
            self.delete_credit(credit)

        self.print_message(f'\nDeleting Disbursments older than {cutoff_date}...')
        disbursements_to_delete = Disbursement.objects.filter(created__lt=cutoff_date)
        for disbursement in disbursements_to_delete:
            self.delete_disbursement(disbursement)

        self.print_message(f'\nDeleting Transactions older than {cutoff_date}...')
        records_deleted = Transaction.objects.filter(received_at__lt=cutoff_date).delete()
        self.print_message(f'Records deleted: {records_deleted}.', 1)

        self.print_message(f'\nDeleting Payment older than {cutoff_date}...')
        records_deleted = Payment.objects.filter(modified__lt=cutoff_date).delete()
        self.print_message(f'Records deleted: {records_deleted}.', 1)

        self.print_message(f'\nDeleting UserEvent older than {cutoff_date}...')
        records_deleted = UserEvent.objects.filter(timestamp__lt=cutoff_date).delete()
        self.print_message(f'Records deleted: {records_deleted}.', 1)

    @transaction.atomic
    def delete_credit(self, credit: Credit):
        depth = 1
        self.print_message(f'Deleting Credit {credit}...', depth)

        self.print_message('Deleting associated Events...', depth+1)
        self.delete_events(credit.creditevent_set.all(), depth+2)

        billing_address_to_check = None
        # Some old credits may not have a (card) payment, e.g. bank transfers
        if hasattr(credit, 'payment'):
            billing_address_to_check = credit.payment.billing_address

        record_deleted = credit.delete()
        self.print_message(f'Records deleted: {record_deleted}.', depth+1)

        sender_profile = credit.sender_profile
        if sender_profile:
            if not sender_profile.credits.exists():
                self.print_message(f'SenderProfile {sender_profile} has no credits, deleting...', depth+1)

                self.print_message('Deleting associated Events...', depth+2)
                self.delete_events(sender_profile.senderprofileevent_set.all(), depth+3)

                self.print_message(
                    f"Deleting SenderProfile's SavedSearches '*/senders/{sender_profile.id}/*'...",
                    depth+2,
                )
                record_deleted = SavedSearch.objects \
                    .filter(site_url__contains=f'/senders/{sender_profile.id}/') \
                    .delete()
                self.print_message(f'Records deleted: {record_deleted}.', depth+3)

                bank_accounts_to_check = [
                    sender_details.sender_bank_account

                    for sender_details in sender_profile.bank_transfer_details.all()
                ]

                record_deleted = sender_profile.delete()
                self.print_message(f'Records deleted: {record_deleted}.', depth+2)

                self.delete_orphan_bank_accounts(bank_accounts_to_check, depth+2)
                self.delete_orphan_billing_address(billing_address_to_check, depth+2)
            else:
                SenderProfile.objects \
                    .filter(id=sender_profile.id) \
                    .recalculate_totals()
                self.print_message(f'SenderProfile {sender_profile} updated.', depth+1)

        if credit.prisoner_profile:
            self.update_or_delete_prisoner_profile(credit.prisoner_profile, depth+1)

    @transaction.atomic
    def delete_disbursement(self, disbursement: Disbursement):
        depth = 1
        self.print_message(f'Deleting Disbursement {disbursement}...', depth)

        self.print_message('Deleting associated Events...', depth+1)
        self.delete_events(disbursement.disbursementevent_set.all(), depth+2)

        record_deleted = disbursement.delete()
        self.print_message(f'Records deleted: {record_deleted}.', depth+1)

        recipient_profile = disbursement.recipient_profile
        if recipient_profile:
            if not recipient_profile.disbursements.exists():
                self.print_message(f'RecipientProfile {recipient_profile} has no disbursements, deleting...', depth+1)

                self.print_message('Deleting associated Events...', depth+2)
                self.delete_events(recipient_profile.recipientprofileevent_set.all(), depth+3)

                bank_accounts_to_check = [
                    recipient_details.recipient_bank_account

                    for recipient_details in recipient_profile.bank_transfer_details.all()
                ]

                record_deleted = recipient_profile.delete()
                self.print_message(f'Records deleted: {record_deleted}.', depth+2)

                self.delete_orphan_bank_accounts(bank_accounts_to_check, depth+2)
            else:
                RecipientProfile.objects \
                    .filter(id=recipient_profile.id) \
                    .recalculate_totals()
                self.print_message(f'RecipientProfile {recipient_profile} updated.', depth+1)

        if disbursement.prisoner_profile:
            self.update_or_delete_prisoner_profile(disbursement.prisoner_profile, depth+1)

    def update_or_delete_prisoner_profile(self, prisoner_profile: PrisonerProfile | None, depth):
        if not prisoner_profile.credits.exists() and not prisoner_profile.disbursements.exists():
            self.print_message(
                f'PrisonerProfile {prisoner_profile} has no credits nor disbursements, deleting...',
                depth,
            )

            self.print_message('Deleting associated Events...', depth+1)
            self.delete_events(prisoner_profile.prisonerprofileevent_set.all(), depth+2)

            self.print_message(
                f"Deleting PrisoneProfile's SavedSearches '*/prisoners/{prisoner_profile.id}/*'...",
                depth+1,
            )
            record_deleted = SavedSearch.objects \
                .filter(site_url__contains=f'/prisoners/{prisoner_profile.id}/') \
                .delete()
            self.print_message(f'Records deleted: {record_deleted}.', depth+2)

            record_deleted = prisoner_profile.delete()
            self.print_message(f'Records deleted: {record_deleted}.', depth+1)
        else:
            PrisonerProfile.objects \
                        .filter(id=prisoner_profile.id) \
                        .recalculate_totals()
            self.print_message(f'PrisonerProfile {prisoner_profile} updated.', depth)

    EventType = CreditEvent | DisbursementEvent | PrisonerProfileEvent | RecipientProfileEvent | SenderProfileEvent

    def delete_events(self, thing_events: Sequence[EventType], depth):
        for thing_event in thing_events:
            event = thing_event.event
            self.print_message(f'Deleting Event {event}...', depth)
            record_deleted = event.delete()
            self.print_message(f'Records deleted: {record_deleted}.', depth+1)

    def delete_orphan_bank_accounts(self, bank_accounts: Sequence[BankAccount], depth):
        for bank_account in bank_accounts:
            if not bank_account.senders.exists() and not bank_account.recipients.exists():
                self.print_message(f'BankAccount {bank_account} has no senders nor recipients, deleting...', depth)
                record_deleted = bank_account.delete()
                self.print_message(f'Records deleted: {record_deleted}.', depth+1)

    def delete_orphan_billing_address(self, billing_address: BillingAddress | None, depth):
        if billing_address:
            billing_address.refresh_from_db()

            payments = billing_address.payment_set
            if not billing_address.debit_card_sender_details_id and not payments.exists():
                self.print_message(
                    f'BillingAddress {billing_address} has no debit_card_sender_details nor credits, deleting...',
                    depth,
                )

                record_deleted = billing_address.delete()
                self.print_message(f'Records deleted: {record_deleted}.', depth+1)
