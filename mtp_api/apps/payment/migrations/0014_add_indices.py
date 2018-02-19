from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payment', '0013_billingaddress_debit_card_sender_details'),
    ]
    operations = [
        migrations.AlterField(
            model_name='payment',
            name='processor_id',
            field=models.CharField(blank=True, db_index=True, max_length=250, null=True),
        ),
        migrations.AlterField(
            model_name='payment',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('failed', 'Failed'), ('taken', 'Taken')], db_index=True, default='pending', max_length=50),
        ),
    ]
