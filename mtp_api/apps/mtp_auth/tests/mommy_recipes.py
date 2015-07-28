from model_mommy import timezone
from model_mommy.mommy import make
from model_mommy.recipe import Recipe, foreign_key

from django.contrib.auth.models import User, Group
from django.utils.text import slugify
from django.utils.crypto import get_random_string

from mtp_auth.models import PrisonUserMapping


NOW = lambda: timezone.now()
prison_user = Recipe(User,
                     email=None,
                     is_staff=False,
                     is_active=True,
                     is_superuser=False,
                     last_login=NOW,
                     created=NOW)

prison_user_mapping = Recipe(PrisonUserMapping,
                             user=foreign_key(prison_user))


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
