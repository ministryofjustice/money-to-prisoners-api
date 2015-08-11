# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0003_remove_prisonerlocation_upload_counter'),
    ]

    operations = [
        migrations.AddField(
            model_name='prisonerlocation',
            name='prisoner_hash',
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
