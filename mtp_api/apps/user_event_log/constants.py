from django.db import models
from django.utils.translation import gettext_lazy

class USER_EVENT_KINDS(models.TextChoices):
    NOMS_OPS_SEARCH = 'noms_ops_search', gettext_lazy('Search in Intelligence Tool')
