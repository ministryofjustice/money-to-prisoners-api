from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0014_auto_20180220_1440'),
    ]
    operations = [
        migrations.AddField(
            model_name='disbursement',
            name='remittance_description',
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
