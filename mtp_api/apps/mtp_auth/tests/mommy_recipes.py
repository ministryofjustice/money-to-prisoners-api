from model_mommy import timezone
from model_mommy.mommy import make, make_recipe
from model_mommy.recipe import Recipe, foreign_key

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.text import slugify
from django.utils.crypto import get_random_string

from mtp_auth.models import PrisonUserMapping

User = get_user_model()

NOW = lambda: timezone.now()
basic_user = Recipe(
    User,
    is_staff=False,
    is_active=True,
    is_superuser=False,
    last_login=NOW
)

prison_user_mapping = Recipe(
    PrisonUserMapping, user=foreign_key(basic_user)
)


def create_prison_user_mapping(prison):
    prison_clerk_group = Group.objects.get(name='PrisonClerk')
    name_and_password = 'test_' + slugify(prison).replace('-', '_')

    # if first user
    #   username/password == test_<prison_name>.replace('-', '_')
    # else:
    #   username/password == test_<prison_name>.replace('-', '_')_<random_string>
    suffix = ''
    if User.objects.filter(username=name_and_password).exists():
        suffix = '_%s' % get_random_string(length=5)
    name_and_password += suffix

    pu = make(
        'PrisonUserMapping',
        user__username=name_and_password,
        prisons=[prison]
    )
    pu.user.set_password(name_and_password)
    pu.user.save()
    pu.user.groups.add(prison_clerk_group)
    return pu


def create_prisoner_location_admins():
    name_and_password = 'prisoner_location_admin'

    prisoner_location_admin_group = Group.objects.get(name='PrisonerLocationAdmin')
    plu = basic_user.make(
        username=name_and_password
    )
    plu.set_password(name_and_password)
    plu.save()
    plu.groups.add(prisoner_location_admin_group)

    return [plu]
