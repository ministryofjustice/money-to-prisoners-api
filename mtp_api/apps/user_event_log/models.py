from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from user_event_log.constants import USER_EVENT_KINDS


class FlexibleDjangoJSONEncoder(DjangoJSONEncoder):
    """
    A more flexible version of DjangoJSONEncoder which never raises TypeError.
    If DjangoJSONEncoder cannot encode the object, it uses its pk property or
    defaults to using its str() representation.
    """

    def default(self, o):
        """
        Return the DjangoJSONEncoder default OR o.id OR str(o) in this order.
        """
        try:
            return super().default(o)
        except TypeError:
            if hasattr(o, 'pk'):
                return o.pk
        return str(o)


class UserEvent(models.Model):
    """
    Used to keep a record of specific events that have occurred while the user was using the system.

    Not intended as a replacement for logging, but for cases where we need to record data in a
    more structured fashion and retain it for a longer period of time.
    """

    id = models.BigAutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_events',
    )
    kind = models.CharField(max_length=254, choices=USER_EVENT_KINDS)
    api_url_path = models.CharField(verbose_name='API URL path', max_length=5000, db_index=True)
    data = JSONField(null=True, encoder=FlexibleDjangoJSONEncoder)

    def __str__(self):
        """Human-friendly string representation."""
        return f'{self.timestamp} – {self.user} – {self.get_kind_display()}'

    class Meta:
        ordering = ('-timestamp', '-pk')
