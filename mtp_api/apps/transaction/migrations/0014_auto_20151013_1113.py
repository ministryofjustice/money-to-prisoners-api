from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0013_transaction_prisoner_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='reconciled',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(max_length=50, choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited'), ('refunded', 'Refunded'), ('reconciled', 'Reconciled')]),
        ),
    ]
