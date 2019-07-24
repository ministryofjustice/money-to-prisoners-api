import warnings

from django.conf import settings
from django.db import migrations


def link_credits(apps, _):
    if settings.ENVIRONMENT == 'prod':
        warnings.warn('Remember to run a manual update to link credits to security profiles')
        return


class Migration(migrations.Migration):
    dependencies = [
        ('credit', '0016_link_to_credits'),
    ]
    operations = [
        migrations.RunPython(code=link_credits, reverse_code=migrations.RunPython.noop),
    ]
