import logging

from django.db.transaction import atomic
from django.core.management import BaseCommand

from credit.models import Credit
from security.models import (
    SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails,
    PrisonerProfile, SecurityDataUpdate, CardholderName, SenderEmail
)

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbose = False

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--batch-size', type=int, default=200,
                            help='Number of credits to process in one atomic transaction')
        parser.add_argument('--recreate', action='store_true', help='Deletes existing sender and prisoner profiles')

    def handle(self, **options):
        self.verbose = options['verbosity'] > 1
        if options['recreate']:
            self.delete_profiles()
        batch_size = options['batch_size']
        assert batch_size > 0

        queryset = Credit.objects.order_by('pk')
        try:
            last_updated_pk = SecurityDataUpdate.objects.latest().max_credit_pk
            new_credits = queryset.filter(pk__gt=last_updated_pk)
        except SecurityDataUpdate.DoesNotExist:
            new_credits = queryset.all()

        new_credits_count = new_credits.count()
        if not new_credits_count:
            self.stdout.write(self.style.SUCCESS('No new credits'))
            return
        else:
            self.stdout.write('Updating profiles for %d new credits' % new_credits_count)

        try:
            processed_count = 0
            for offset in range(0, new_credits_count, batch_size):
                batch = slice(offset, min(offset + batch_size, new_credits_count))
                processed_count += self.process_batch(new_credits[batch])
                if self.verbose:
                    self.stdout.write('Processed %d credits' % processed_count)
        finally:
            self.stdout.write('Updating prisoner profiles for current locations')
            PrisonerProfile.objects.update_current_prisons()

        self.stdout.write(self.style.SUCCESS('Done'))

    @atomic()
    def process_batch(self, new_credits):
        credit = None
        for credit in new_credits:
            self.create_or_update_profiles(credit)
        if credit:
            SecurityDataUpdate(max_credit_pk=credit.pk).save()
        return len(new_credits)

    def create_or_update_profiles(self, credit):
        sender_profile = self.create_or_update_sender_profile(credit)
        if credit.prison:
            self.create_or_update_prisoner_profile(credit, sender_profile)

    def create_or_update_sender_profile(self, credit):
        if hasattr(credit, 'transaction'):
            sender_profile = self.create_or_update_bank_transfer(credit)
        elif hasattr(credit, 'payment'):
            sender_profile = self.create_or_update_debit_card(credit)
        else:
            logger.error('Credit %s does not have a payment nor transaction' % credit.pk)
            return

        sender_profile.credit_count += 1
        sender_profile.credit_total += credit.amount
        sender_profile.save()
        return sender_profile

    def create_or_update_bank_transfer(self, credit):
        try:
            sender_profile = SenderProfile.objects.get(
                bank_transfer_details__sender_name=credit.sender_name,
                bank_transfer_details__sender_sort_code=credit.sender_sort_code,
                bank_transfer_details__sender_account_number=credit.sender_account_number,
                bank_transfer_details__sender_roll_number=credit.sender_roll_number
            )
        except SenderProfile.DoesNotExist:
            if self.verbose:
                self.stdout.write('Creating bank transfer profile for %s' % credit.sender_name)
            sender_profile = SenderProfile()
            sender_profile.save()
            sender_profile.bank_transfer_details.add(
                BankTransferSenderDetails(
                    sender_name=credit.sender_name,
                    sender_sort_code=credit.sender_sort_code,
                    sender_account_number=credit.sender_account_number,
                    sender_roll_number=credit.sender_roll_number
                ),
                bulk=False
            )
        return sender_profile

    def create_or_update_debit_card(self, credit):
        sender_name = credit.sender_name or ''
        sender_email = credit.payment.email or ''
        try:
            sender_details = DebitCardSenderDetails.objects.get(
                card_number_last_digits=credit.card_number_last_digits,
                card_expiry_date=credit.card_expiry_date
            )
            sender_profile = sender_details.sender
            if sender_name:
                try:
                    sender_details.cardholder_names.get(
                        name=sender_name
                    )
                except CardholderName.DoesNotExist:
                    sender_details.cardholder_names.add(
                        CardholderName(name=sender_name),
                        bulk=False
                    )
            if sender_email:
                try:
                    sender_details.sender_emails.get(
                        email=sender_email
                    )
                except SenderEmail.DoesNotExist:
                    sender_details.sender_emails.add(
                        SenderEmail(email=sender_email),
                        bulk=False
                    )
        except DebitCardSenderDetails.DoesNotExist:
            if self.verbose:
                self.stdout.write('Creating debit card profile for ****%s, %s' % (credit.card_number_last_digits,
                                                                                  sender_name))
            sender_profile = SenderProfile()
            sender_profile.save()
            sender_profile.debit_card_details.add(
                DebitCardSenderDetails(
                    card_number_last_digits=credit.card_number_last_digits,
                    card_expiry_date=credit.card_expiry_date,
                ),
                bulk=False
            )
            if sender_name:
                sender_profile.debit_card_details.first().cardholder_names.add(
                    CardholderName(name=sender_name), bulk=False
                )
            if sender_email:
                sender_profile.debit_card_details.first().sender_emails.add(
                    SenderEmail(email=sender_email), bulk=False
                )
        return sender_profile

    def create_or_update_prisoner_profile(self, credit, sender):
        try:
            prisoner_profile = PrisonerProfile.objects.get(
                prisoner_number=credit.prisoner_number,
                prisoner_dob=credit.prisoner_dob
            )
        except PrisonerProfile.DoesNotExist:
            if self.verbose:
                self.stdout.write('Creating prisoner profile for %s' % credit.prisoner_number)
            prisoner_profile = PrisonerProfile(
                prisoner_name=credit.prisoner_name,
                prisoner_number=credit.prisoner_number,
                prisoner_dob=credit.prisoner_dob
            )
            prisoner_profile.save()

        prisoner_profile.credit_count += 1
        prisoner_profile.credit_total += credit.amount
        prisoner_profile.prisons.add(credit.prison)
        prisoner_profile.senders.add(sender)
        prisoner_profile.save()
        return prisoner_profile

    @atomic()
    def delete_profiles(self):
        from django.apps import apps
        from django.core.management.color import no_style
        from django.db import connection

        PrisonerProfile.objects.all().delete()
        SenderProfile.objects.all().delete()
        SecurityDataUpdate.objects.all().delete()

        security_app = apps.app_configs['security']
        with connection.cursor() as cursor:
            for reset_sql in connection.ops.sequence_reset_sql(no_style(), security_app.get_models()):
                cursor.execute(reset_sql)
