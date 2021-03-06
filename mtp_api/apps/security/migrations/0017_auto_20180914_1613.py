# Generated by Django 2.0.8 on 2018-09-14 15:13

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0016_auto_20180914_1551'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='banktransfersenderdetails',
            name='sender_account_number',
        ),
        migrations.RemoveField(
            model_name='banktransfersenderdetails',
            name='sender_roll_number',
        ),
        migrations.RemoveField(
            model_name='banktransfersenderdetails',
            name='sender_sort_code',
        ),
        migrations.AlterField(
            model_name='banktransfersenderdetails',
            name='sender_bank_account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='senders', to='security.BankAccount'),
        ),
    ]
