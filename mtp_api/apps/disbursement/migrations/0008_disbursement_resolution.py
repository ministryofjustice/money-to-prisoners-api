from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0007_auto_20180108_1230'),
    ]
    operations = [
        migrations.AlterField(
            model_name='disbursement',
            name='resolution',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('rejected', 'Rejected'), ('preconfirmed', 'Pre-confirmed'),
                         ('confirmed', 'Confirmed'), ('sent', 'Sent')], default='pending', max_length=50),
        ),
    ]
