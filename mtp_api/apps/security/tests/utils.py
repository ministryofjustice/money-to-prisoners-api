import logging
import random

import faker
from django.db import transaction
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string

from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from prison.models import Prison
from payment.models import Payment, PAYMENT_STATUS
from payment.tests.utils import create_fake_sender_data, generate_payments
from prison.tests.utils import random_prisoner_number
from security.models import Check, DebitCardSenderDetails, PrisonerProfile, SenderProfile
from django.db.models import Count

fake = faker.Faker(locale='en_GB')

logger = logging.getLogger('MTP')

PAYMENT_FILTERS_FOR_INVALID_CHECK = dict(
    status=PAYMENT_STATUS.PENDING,
    credit=dict(
        resolution=CREDIT_RESOLUTION.INITIAL,
        owner_id=None,
        sender_profile_id=None,
        prisoner_profile_id=None,
        prison_id__isnull=False
    )
)

PAYMENT_FILTERS_FOR_VALID_CHECK = dict(
    status=PAYMENT_STATUS.PENDING,
    email__isnull=False,
    cardholder_name__isnull=False,
    card_number_first_digits__isnull=False,
    card_number_last_digits__isnull=False,
    card_expiry_date__isnull=False,
    billing_address__isnull=False,
    billing_address__debit_card_sender_details__isnull=False,
    credit__isnull=False,
    credit=dict(
        resolution=CREDIT_RESOLUTION.INITIAL,
        # This only works because get_or_create ignores values with __ in any call to create()
        # these values must be included in the defaults if NOT NULL
        owner__isnull=True,
        prisoner_number__isnull=False,
        prisoner_name__isnull=False,
        sender_profile__isnull=False,
        prison_id__isnull=False,
    )
)


def _get_payment_values(payment_filters, cardholder_name):
    return dict(
        card_number_first_digits=get_random_string(6, '0123456789'),
        card_number_last_digits=get_random_string(4, '0123456789'),
        cardholder_name=cardholder_name,
        card_expiry_date=fake.date_time_between(start_date='now', end_date='+5y').strftime('%m/%y'),
        **{
            key: val for key, val in payment_filters.items()
            if '__' not in key
        }
    )


def _get_credit_values(credit_filters, sender_profile_id, prisoner_profile_id, prisoner_name):
    return dict(
        {
            'amount': random.randint(100, 1000000),
            'prisoner_number': random_prisoner_number(),
            'prisoner_name': prisoner_name,
            'prisoner_profile_id': prisoner_profile_id,
            'sender_profile_id': sender_profile_id,
            'prison_id': random.choice(Prison.objects.all()).nomis_id
        },
        **{
            key: val for key, val in credit_filters.items()
            if '__' not in key
        }
    )


def generate_checks(
    number_of_checks=1, specific_payments_to_check=tuple(), create_invalid_checks=True,
    number_of_prisoners_to_use=5, number_of_senders_to_use=5
):
    checks = []
    fake_prisoner_names = {pp_id[0]: fake.name() for pp_id in PrisonerProfile.objects.values_list('id')}
    fake_sender_names = {sp_id[0]: fake.name() for sp_id in SenderProfile.objects.values_list('id')}

    fiu = Group.objects.get(name='FIU').user_set.first()
    prisoner_profiles = PrisonerProfile.objects.all()
    if not prisoner_profiles:
        logger.warning('No prisoner profiles present!')
    for prisoner_profile in prisoner_profiles:
        prisoner_profile.monitoring_users.add(fiu)
        prisoner_profile.save()

    sender_profiles = SenderProfile.objects.all()
    if not sender_profiles:
        logger.warning('No sender profiles present!')
    for sender_profile in sender_profiles:
        monitored_instance = None
        if sender_profile.debit_card_details.count():
            monitored_instance = sender_profile.debit_card_details.first()
        elif sender_profile.bank_transfer_details.count():
            monitored_instance = sender_profile.bank_transfer_details.first().sender_bank_account
        if monitored_instance:
            monitored_instance.monitoring_users.add(fiu)
            monitored_instance.save()

    if create_invalid_checks:
        filters = [PAYMENT_FILTERS_FOR_INVALID_CHECK]
    else:
        filters = []
    filters.extend([
        *([PAYMENT_FILTERS_FOR_VALID_CHECK] * number_of_checks),
        *specific_payments_to_check
    ])

    for filter_set in filters:
        filter_set = filter_set.copy()
        if (
            not sender_profiles or (
                'sender_profile_id' in filter_set.get('credit', [])
                and not filter_set['credit']['sender_profile_id']
            )
        ):
            sender_profile_id = None
            cardholder_name = None
        else:
            sender_profile_id = random.choice(
                SenderProfile.objects.filter(
                    debit_card_details__isnull=False
                ).annotate(
                    cred_count=Count('credits')
                ).order_by('-cred_count').all()[:number_of_senders_to_use]
            ).id
            cardholder_name = fake_sender_names[sender_profile_id]
        if (
            not prisoner_profiles or (
                'prisoner_profile_id' in filter_set['credit']
                and not filter_set['credit']['prisoner_profile_id']
            )
        ):
            prisoner_profile_id = None
            prisoner_name = None
        else:
            prisoner_profile_id = random.choice(
                PrisonerProfile.objects.annotate(
                    cred_count=Count('credits')
                ).order_by('-cred_count').all()[:number_of_prisoners_to_use]
            ).id
            prisoner_name = fake_prisoner_names[prisoner_profile_id]
        credit_filters = filter_set.pop('credit', {})
        candidate_payment = Payment.objects.filter(
            credit=Credit.objects.filter(
                **credit_filters
            ).get_or_create(
                **_get_credit_values(
                    credit_filters,
                    sender_profile_id,
                    prisoner_profile_id,
                    prisoner_name
                )
            )[0],
            **filter_set
        ).first()
        if not candidate_payment:
            candidate_payment = generate_payments(payment_batch=1, overrides=dict(
                credit=_get_credit_values(
                    credit_filters,
                    sender_profile_id,
                    prisoner_profile_id,
                    prisoner_name
                ),
                **_get_payment_values(
                    filter_set,
                    cardholder_name
                )
            ))[0]
        candidate_payment.credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
        checks.append(Check.objects.create_for_credit(candidate_payment.credit))

    return checks


@transaction.atomic()
def generate_prisoner_profiles_from_prisoner_locations(prisoner_locations):
    # TODO remove this when updated to django 3.* and `ignore_conflicts` kwarg available
    existing_prisoner_profiles = PrisonerProfile.objects.values_list('prisoner_number', flat=True)
    prisoner_locations_filtered = list(
        filter(
            lambda pl: pl.prisoner_number not in existing_prisoner_profiles,
            prisoner_locations
        )
    )
    if not prisoner_locations_filtered:
        return prisoner_locations_filtered
    prisoner_profiles = PrisonerProfile.objects.bulk_create(
        [
            PrisonerProfile(
                prisoner_name=prisoner_location.prisoner_name,
                prisoner_number=prisoner_location.prisoner_number,
                single_offender_id=prisoner_location.single_offender_id,
                prisoner_dob=prisoner_location.prisoner_dob,
                current_prison_id=prisoner_location.prison_id
            )
            for prisoner_location in prisoner_locations_filtered
        ]
    )
    suitable_credits = Credit.objects.filter(
        payment__isnull=False
    )
    suitable_credits_count = suitable_credits.count()
    assert suitable_credits_count >= len(prisoner_profiles), f'{suitable_credits_count} < {len(prisoner_profiles)}'
    for suitable_credit in suitable_credits:
        prisoner_profile = random.choice(prisoner_profiles)
        suitable_credit.prison = prisoner_profile.current_prison
        suitable_credit.prisoner_name = prisoner_profile.prisoner_name
        suitable_credit.prisoner_dob = prisoner_profile.prisoner_dob
        suitable_credit.single_offender_id = prisoner_profile.single_offender_id
        suitable_credit.save()

        payment = suitable_credit.payment
        payment.recipient_name = prisoner_profile.prisoner_name
        payment.save()

        prisoner_profile.credits.add(suitable_credit)
        prisoner_profile.save()
    return prisoner_profiles


@transaction.atomic()
def generate_sender_profiles_from_payments(number_of_senders):
    print('Querying for payments from which to generate sender profiles')
    suitable_payments = Payment.objects.filter(
        email__isnull=False,
        cardholder_name__isnull=False,
        card_number_first_digits__isnull=False,
        card_number_last_digits__isnull=False,
        card_expiry_date__isnull=False,
        billing_address__isnull=False,
        credit__isnull=False,
    ).distinct(
        'card_number_last_digits',
        'card_expiry_date',
        'billing_address__postcode'
    ).order_by(
        'card_number_last_digits',
        'card_expiry_date',
        'billing_address__postcode'
    )
    assert len(suitable_payments) >= number_of_senders, f'{len(suitable_payments)} < {number_of_senders}'

    suitable_payments_without_dcsd = suitable_payments.filter(
        billing_address__debit_card_sender_details__isnull=True,
    )
    #  suitable_payments_without_dcsd_count = suitable_payments_without_dcsd.count()
    print('Generating sender profiles')
    senders = [SenderProfile() for _ in range(number_of_senders)]
    print('Commiting SenderProfiles')
    SenderProfile.objects.bulk_create(
        senders,
        batch_size=500
    )
    suitable_payments_iter = iter(suitable_payments)

    print('Assigning Credits to Senders')
    for sender in senders:
        payment = next(suitable_payments_iter)
        sender.credits.add(payment.credit)
        sender.save()

    # TODO there is still some work to do to generate
    # BankTransferSenderDetails, but this code should be compatible with
    # generation of these, but it needs to happen between the creation of
    # SenderProfiles and the query on the line below
    all_orphaned_senders = SenderProfile.objects.filter(
        bank_transfer_details__isnull=True,
        debit_card_details__isnull=True
    )
    all_orphaned_senders_count = all_orphaned_senders.count()
    if not all_orphaned_senders_count:
        return []
    print(f'Generating data for {all_orphaned_senders_count} DebitCardSenderDetails')
    dcsd_data = create_fake_sender_data(all_orphaned_senders_count)
    all_orphaned_senders_iter = iter(all_orphaned_senders)
    print('Commiting DebitCardSenderDetails')
    dcsd_instances = DebitCardSenderDetails.objects.bulk_create(
        [
            DebitCardSenderDetails(
                postcode=dcsd_datum['billing_address']['postcode'],
                card_number_last_digits=dcsd_datum['card_number_last_digits'],
                card_expiry_date=dcsd_datum['card_expiry_date'],
                sender=next(all_orphaned_senders_iter)
            )
            for dcsd_datum in dcsd_data
        ],
        batch_size=500
    )
    dcsd_instances_iter = iter(dcsd_instances)
    print('Assigning DebitCardSenderDetails to Payments')
    for payment in suitable_payments_without_dcsd:
        dcsd = next(dcsd_instances_iter)
        billing_address = payment.billing_address
        billing_address.debit_card_sender_detail = dcsd
        billing_address.save()

    return senders
