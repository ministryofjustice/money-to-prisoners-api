from django.db import models
from django.utils.translation import gettext_lazy

class CHECK_STATUS(models.TextChoices):
    PENDING = 'pending', gettext_lazy('Pending')
    ACCEPTED = 'accepted', gettext_lazy('Accepted')
    REJECTED = 'rejected', gettext_lazy('Rejected')
