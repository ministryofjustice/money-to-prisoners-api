# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('upload_counter', models.PositiveIntegerField()),
                ('prisoner_number', models.CharField(max_length=250, blank=True)),
                ('prisoner_name', models.CharField(max_length=250, blank=True)),
                ('prisoner_dob', models.DateField(null=True, blank=True)),
                ('amount', models.PositiveIntegerField()),
                ('sender_bank_reference', models.CharField(max_length=250, blank=True)),
                ('sender_customer_reference', models.CharField(max_length=250, blank=True)),
                ('reference', models.TextField(blank=True)),
                ('received_at', models.DateTimeField()),
                ('prison', models.ForeignKey(to='prison.Prison', null=True, blank=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
