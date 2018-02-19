from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0012_index_prisoner_number'),
    ]
    operations = [
        migrations.AlterField(
            model_name='disbursement',
            name='amount',
            field=models.PositiveIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='disbursement',
            name='method',
            field=models.CharField(choices=[('bank_transfer', 'Bank transfer'), ('cheque', 'Cheque')], db_index=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='disbursement',
            name='resolution',
            field=models.CharField(choices=[('pending', 'Pending'), ('rejected', 'Rejected'), ('preconfirmed', 'Pre-confirmed'), ('confirmed', 'Confirmed'), ('sent', 'Sent')], db_index=True, default='pending', max_length=50),
        ),
    ]
