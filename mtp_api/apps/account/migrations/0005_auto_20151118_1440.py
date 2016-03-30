# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('account', '0004_auto_20151110_1038'),
    ]

    operations = [
        migrations.AddField(
            model_name='batch',
            name='user',
            field=models.ForeignKey(null=True, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
    ]
