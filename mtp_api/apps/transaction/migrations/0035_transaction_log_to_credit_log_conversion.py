# Generated by Django 1.9.4 on 2016-05-03 14:32
from django.db import migrations


def convert_to_credit_logs(apps, schema_editor):
    TransactionLog = apps.get_model('transaction', 'Log')
    CreditLog = apps.get_model('credit', 'Log')
    for transaction_log in TransactionLog.objects.all():
        credit = transaction_log.transaction.credit
        if credit:
            credit_log = CreditLog(
                credit=credit,
                user=transaction_log.user,
                action=transaction_log.action,
                created=transaction_log.created,
            )
            credit_log.save()


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0034_transaction_to_credit_conversion'),
        ('credit', '0002_auto_20160503_1531'),
    ]

    operations = [
        migrations.RunPython(convert_to_credit_logs)
    ]
