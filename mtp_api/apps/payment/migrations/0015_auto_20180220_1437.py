# Generated by Django 1.11.10 on 2018-02-20 14:37
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0014_add_indices'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['modified'], name='payment_pay_modifie_c1f247_idx'),
        ),
    ]
