# Generated by Django 1.9.4 on 2016-11-01 15:36
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0009_prison_associations'),
    ]

    operations = [
        migrations.AddField(
            model_name='prison',
            name='pre_approval_required',
            field=models.BooleanField(default=False),
        ),
    ]
