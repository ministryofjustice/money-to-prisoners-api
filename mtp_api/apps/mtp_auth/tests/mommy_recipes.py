from django.utils.text import slugify
from model_mommy import timezone
from model_mommy.recipe import Recipe, foreign_key
from model_mommy.mommy import make
from django.contrib.auth.models import User
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
    name_and_password = 'test_' + slugify(prison).replace('-', '_')
    if not User.objects.filter(username=name_and_password).exists():
        pu = make('PrisonUserMapping',
                  user__username=name_and_password,
                  prisons=[prison]
                  )
        pu.user.set_password(name_and_password)
        pu.user.save()
