from django.db import models
from django.utils.translation import gettext_lazy as _


class UserEventKind(models.TextChoices):
    noms_ops_search = 'noms_ops_search', _('Search in Intelligence Tool')
