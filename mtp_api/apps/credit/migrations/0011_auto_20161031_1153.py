# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-10-31 11:53
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credit', '0010_comment'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='credit',
            options={'get_latest_by': 'received_at', 'ordering': ('received_at',), 'permissions': (('view_credit', 'Can view credit'), ('view_any_credit', 'Can view any credit'), ('lock_credit', 'Can lock credit'), ('unlock_credit', 'Can unlock credit'), ('patch_credited_credit', 'Can patch credited credit'), ('review_credit', 'Can review credit'))},
        ),
        migrations.AddField(
            model_name='credit',
            name='reviewed',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited'), ('refunded', 'Refunded'), ('reconciled', 'Reconciled'), ('reviewed', 'Reviewed')], max_length=50),
        ),
    ]