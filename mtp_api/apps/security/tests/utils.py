import logging
import random

import faker
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string

from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from prison.models import Prison
from payment.models import BillingAddress, Payment, PAYMENT_STATUS
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
    credit=dict(
        resolution=CREDIT_RESOLUTION.INITIAL,
        # This only works because get_or_create ignores values with __ in any call to create()
        # these values must be included in the defaults if NOT NULL
        owner__isnull=True,
        prisoner_number__isnull=False,
        prisoner_name__isnull=False,
        sender_profile__isnull=False,
        prison_id__isnull=False
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


def generate_checks(number_of_checks=1, specific_payments_to_check=tuple()):
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

    filters = [
        PAYMENT_FILTERS_FOR_INVALID_CHECK,
        *([PAYMENT_FILTERS_FOR_VALID_CHECK] * number_of_checks),
        *specific_payments_to_check
    ]

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
                ).order_by('-cred_count').all()[:5]
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
                ).order_by('-cred_count').all()[:5]
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


def generate_prisoner_profiles_from_prisoner_locations(prisoner_locations):
    # TODO remove this when updated to django 3.* and `ignore_conficts` kwarg available
    existing_prisoner_profiles = PrisonerProfile.objects.values('prisoner_number')
    prisoner_locations_filtered = filter(
        lambda pl: pl.prisoner_number in existing_prisoner_profiles,
        prisoner_locations
    )
    return PrisonerProfile.objects.bulk_create(
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


def generate_sender_profiles_from_prisoner_profiles(no_of_senders):
    fake_sender_data = create_fake_sender_data(no_of_senders)
    # Have to do this in an unintuitive direction due to directionality of relationships
    return BillingAddress.objects.bulk_create(
        [
            BillingAddress(
                debit_card_sender_details=DebitCardSenderDetails(
                    postcode=fake_sender_datum['billing_address']['postcode'],
                    card_number_last_digits=fake_sender_datum['card_number_last_digits'],
                    card_expiry_date=fake_sender_datum['card_expiry_date'],
                    sender=SenderProfile()
                ),
                **fake_sender_datum['billing_address'],
            )
            for fake_sender_datum in fake_sender_data
        ],
        batch_size=500
    )
