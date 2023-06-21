# Generated by Django 1.9.4 on 2016-05-17 16:29
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0006_prisonerlocation_prisoner_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='prison',
            name='gender',
            field=models.CharField(blank=True, choices=[('m', 'Male'), ('f', 'Female')], max_length=1),
        ),
        migrations.AddField(
            model_name='prison',
            name='region',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
