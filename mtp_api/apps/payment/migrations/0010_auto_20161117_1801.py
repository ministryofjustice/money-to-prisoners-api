# Generated by Django 1.9.4 on 2016-11-17 18:01
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0009_auto_20161007_1304'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='card_expiry_date',
            field=models.CharField(blank=True, max_length=5, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='card_number_last_digits',
            field=models.CharField(blank=True, max_length=4, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='cardholder_name',
            field=models.CharField(blank=True, max_length=250, null=True),
        ),
    ]
