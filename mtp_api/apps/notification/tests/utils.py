import datetime

from django.utils.crypto import get_random_string
from faker import Faker
from model_bakery import baker

from credit.models import Credit, CREDIT_RESOLUTION
from credit.tests.utils import random_amount
from disbursement.models import Disbursement, DisbursementResolution
from payment.models import Payment
from prison.models import Prison
from prison.tests.utils import random_prisoner_name, random_prisoner_number, random_prisoner_dob
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile,
    DebitCardSenderDetails, BankAccount, BankTransferRecipientDetails,
)

fake = Faker(locale='en_GB')


def make_sender():
    sender = SenderProfile.objects.create()
    baker.make(
        DebitCardSenderDetails,
        sender=sender,
        card_number_last_digits=fake.credit_card_number()[-4:],
        card_expiry_date=fake.credit_card_expire(),
        postcode=fake.postcode(),
    )
    return sender


def make_recipient():
    recipient = RecipientProfile.objects.create()
    bank_account = baker.make(
        BankAccount,
        sort_code=get_random_string(6, '1234567890'),
        account_number=get_random_string(8, '1234567890'),
    )
    baker.make(BankTransferRecipientDetails, recipient=recipient, recipient_bank_account=bank_account)
    return recipient


def make_prisoner():
    return baker.make(
        PrisonerProfile,
        prisoner_name=random_prisoner_name(),
        prisoner_number=random_prisoner_number(),
        prisoner_dob=random_prisoner_dob(),
        current_prison=Prison.objects.order_by('?').first(),
    )


def make_csfreq_credits(today, sender, count):
    debit_card = sender.debit_card_details.first()
    credit_list = []
    for day in range(count):
        credit = baker.make(
            Credit,
            amount=random_amount(),
            sender_profile=sender,
            received_at=today - datetime.timedelta(day),
            resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
        )
        if debit_card:
            payment = baker.make(
                Payment,
                amount=credit.amount,
                card_number_last_digits=debit_card.card_number_last_digits,
                card_expiry_date=debit_card.card_expiry_date,
            )
            payment.credit = credit
            payment.save()
        credit_list.append(credit)
    return credit_list


def make_drfreq_disbursements(today, recipient, count):
    disbursement_list = []
    for day in range(count):
        disbursement = baker.make(
            Disbursement,
            amount=random_amount(),
            recipient_profile=recipient,
            created=today - datetime.timedelta(day),
            resolution=DisbursementResolution.sent,
        )
        disbursement_list.append(disbursement)
    return disbursement_list


def make_csnum_credits(today, prisoner, count, sender_profile=None):
    credit_list = []
    for day in range(count):
        sender = sender_profile or make_sender()
        debit_card = sender.debit_card_details.first()
        credit = baker.make(
            Credit,
            amount=random_amount(),
            sender_profile=sender,
            prisoner_profile=prisoner,
            received_at=today - datetime.timedelta(day),
            resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
        )
        if debit_card:
            payment = baker.make(
                Payment,
                amount=credit.amount,
                card_number_last_digits=debit_card.card_number_last_digits,
                card_expiry_date=debit_card.card_expiry_date,
            )
            payment.credit = credit
            payment.save()
        credit_list.append(credit)
    return credit_list


def make_drnum_disbursements(today, prisoner, count, recipient_profile=None):
    disbursement_list = []
    for day in range(count):
        recipient = recipient_profile or make_recipient()
        disbursement = baker.make(
            Disbursement,
            amount=random_amount(),
            recipient_profile=recipient,
            prisoner_profile=prisoner,
            created=today - datetime.timedelta(day),
            resolution=DisbursementResolution.sent,
        )
        disbursement_list.append(disbursement)
    return disbursement_list


def make_cpnum_credits(today, sender, count, prisoner_profile=None):
    debit_card = sender.debit_card_details.first()
    credit_list = []
    for day in range(count):
        prisoner = prisoner_profile or make_prisoner()
        credit = baker.make(
            Credit,
            amount=random_amount(),
            sender_profile=sender,
            prisoner_profile=prisoner,
            received_at=today - datetime.timedelta(day),
            resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
        )
        if debit_card:
            payment = baker.make(
                Payment,
                amount=credit.amount,
                card_number_last_digits=debit_card.card_number_last_digits,
                card_expiry_date=debit_card.card_expiry_date,
            )
            payment.credit = credit
            payment.save()
        credit_list.append(credit)
    return credit_list


def make_dpnum_disbursements(today, recipient, count, prisoner_profile=None):
    disbursement_list = []
    for day in range(count):
        prisoner = prisoner_profile or make_prisoner()
        disbursement = baker.make(
            Disbursement,
            amount=random_amount(),
            recipient_profile=recipient,
            prisoner_profile=prisoner,
            created=today - datetime.timedelta(day),
            resolution=DisbursementResolution.sent,
        )
        disbursement_list.append(disbursement)
    return disbursement_list
