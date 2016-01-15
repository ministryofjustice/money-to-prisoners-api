from itertools import count
import string

from django.contrib.auth.models import User, Group
from django.utils.text import slugify
from faker import Faker
from model_mommy import timezone
from model_mommy.mommy import make
from model_mommy.recipe import Recipe

fake = Faker(locale='en_GB')

basic_user = Recipe(
    User,
    username=fake.user_name,
    email=fake.safe_email,
    is_staff=False,
    is_active=True,
    is_superuser=False,
    last_login=timezone.now,
    first_name=fake.first_name,
    last_name=fake.last_name,
)


def create_basic_user(name_and_password, groups=(), **user_attributes):
    user = basic_user.make(
        username=name_and_password,
        email=name_and_password + '@mtp.local',
        **user_attributes
    )
    user.set_password(name_and_password)
    user.save()
    for group in groups:
        user.groups.add(group)
    return user


def name_generator(name):
    def suffixes(bases):
        for base in bases:
            for letter in string.ascii_lowercase:
                yield base + letter

    for n in count():
        gen = suffixes([name + '-'])
        for _ in range(n):
            gen = suffixes(gen)
        yield from gen


def create_prison_user_mapping(prison):
    prison_clerk_group = Group.objects.get(name='PrisonClerk')

    name_and_password = base_clerk_name = 'test-' + slugify(prison)
    names = name_generator(name_and_password)
    while User.objects.filter(username=name_and_password).exists():
        name_and_password = next(names)

    name_suffix = name_and_password[len(base_clerk_name):].split('-')[-1]
    user = create_basic_user(
        name_and_password,
        [prison_clerk_group],
        first_name=prison.name,
        last_name='Clerk %s' % name_suffix.upper() if name_suffix else 'Clerk',
    )
    pu = make(
        'mtp_auth.PrisonUserMapping',
        user=user,
        prisons=[prison],
    )
    return pu


def create_prisoner_location_admins():
    name_and_password = 'prisoner-location-admin'

    prisoner_location_admin_group = Group.objects.get(name='PrisonerLocationAdmin')
    plu = create_basic_user(
        name_and_password,
        [prisoner_location_admin_group],
        first_name='Prisoner Location',
        last_name='Admin',
    )

    return [plu]


def create_bank_admins():
    name_and_password = 'bank-admin'

    bank_admin_group = Group.objects.get(name='BankAdmin')
    ba = create_basic_user(
        name_and_password,
        [bank_admin_group],
        first_name='Bank',
        last_name='Admin',
    )

    return [ba]


def create_refund_bank_admins():
    name_and_password = 'refund-bank-admin'

    bank_admin_group = Group.objects.get(name='BankAdmin')
    refund_bank_admin_group = Group.objects.get(name='RefundBankAdmin')
    rba = create_basic_user(
        name_and_password,
        [refund_bank_admin_group, bank_admin_group],
        first_name='Refund',
        last_name='Admin',
    )

    return [rba]


def create_send_money_shared_users():
    name_and_password = 'send-money'
    send_money_group = Group.objects.get(name='SendMoney')
    user = create_basic_user(
        name_and_password,
        [send_money_group],
        first_name='Send Money',
        last_name='Shared',
    )
    return [user]
