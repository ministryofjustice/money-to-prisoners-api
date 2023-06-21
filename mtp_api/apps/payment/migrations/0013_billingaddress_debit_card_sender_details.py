# Generated by Django 1.10.7 on 2017-07-13 15:04
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0013_auto_20170713_1604'),
        ('payment', '0012_auto_20170621_1445'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingaddress',
            name='debit_card_sender_details',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='billing_addresses', to='security.DebitCardSenderDetails'),
        ),
    ]
