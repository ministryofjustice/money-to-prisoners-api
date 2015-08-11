# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0005_populate_prisoner_hash'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prisonerlocation',
            name='prisoner_hash',
            field=models.CharField(max_length=250),
        ),
    ]
