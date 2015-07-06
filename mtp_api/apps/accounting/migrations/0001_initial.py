# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import model_utils.fields
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0002_remove_prisoner_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountingBatch',
            fields=[
                ('id', models.AutoField(auto_created=True, serialize=False, verbose_name='ID', primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(verbose_name='created', default=django.utils.timezone.now, editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(verbose_name='modified', default=django.utils.timezone.now, editable=False)),
                ('batch_reference', models.UUIDField()),
                ('credited', models.BooleanField(default=False)),
                ('discarded', models.BooleanField(db_index=True, default=False)),
                ('locked_by', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('transaction', models.ForeignKey(to='transaction.Transaction')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
