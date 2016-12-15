import logging

from django.db.models import Max
from django.core.management import BaseCommand

from credit.models import Credit
from security.models import (
    SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails,
    PrisonerProfile, SecurityDataUpdate, CardholderName
)

logger = logging.getLogger('mtp')


class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        try:
            last_updated_pk = SecurityDataUpdate.objects.latest().max_credit_pk
            new_credits = Credit.objects.filter(pk__gt=last_updated_pk)
        except SecurityDataUpdate.DoesNotExist:
            new_credits = Credit.objects.all()

        for credit in new_credits:
            self.create_or_update_profiles(credit)

        if len(new_credits):
            new_max_pk = new_credits.aggregate(Max('pk'))['pk__max']
            SecurityDataUpdate(max_credit_pk=new_max_pk).save()

    def create_or_update_profiles(self, credit):
        sender_profile = self.create_or_update_sender_profile(credit)
        if credit.prison:
            self.create_or_update_prisoner_profile(credit, sender_profile)

    def create_or_update_sender_profile(self, credit):
        if hasattr(credit, 'transaction'):
            try:
                sender_profile = SenderProfile.objects.get(
                    bank_transfer_details__sender_name=credit.sender_name,
                    bank_transfer_details__sender_sort_code=credit.sender_sort_code,
                    bank_transfer_details__sender_account_number=credit.sender_account_number,
                    bank_transfer_details__sender_roll_number=credit.sender_roll_number
                )
            except SenderProfile.DoesNotExist:
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
        elif hasattr(credit, 'payment'):
            sender_name = credit.sender_name or ''
            try:
                sender_details = DebitCardSenderDetails.objects.get(
                    card_number_last_digits=credit.card_number_last_digits,
                    card_expiry_date=credit.card_expiry_date
                )
                sender_profile = sender_details.sender
                try:
                    sender_details.cardholder_names.get(
                        name=sender_name
                    )
                except CardholderName.DoesNotExist:
                    sender_details.cardholder_names.add(
                        CardholderName(name=sender_name),
                        bulk=False
                    )
            except DebitCardSenderDetails.DoesNotExist:
                sender_profile = SenderProfile()
                sender_profile.save()
                sender_profile.debit_card_details.add(
                    DebitCardSenderDetails(
                        card_number_last_digits=credit.card_number_last_digits,
                        card_expiry_date=credit.card_expiry_date,
                    ),
                    bulk=False
                )
                sender_profile.debit_card_details.first().cardholder_names.add(
                    CardholderName(name=sender_name), bulk=False
                )
        else:
            logger.error('Credit %s does not have a payment nor transaction' % credit.pk)
            return

        sender_profile.credit_count += 1
        sender_profile.credit_total += credit.amount
        sender_profile.save()
        return sender_profile

    def create_or_update_prisoner_profile(self, credit, sender):
        try:
            prisoner_profile = PrisonerProfile.objects.get(
                prisoner_number=credit.prisoner_number,
                prisoner_dob=credit.prisoner_dob
            )
        except PrisonerProfile.DoesNotExist:
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
