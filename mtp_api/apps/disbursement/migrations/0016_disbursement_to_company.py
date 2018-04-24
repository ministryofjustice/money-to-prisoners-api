from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0015_disbursement_remittance_description'),
    ]
    operations = [
        migrations.AddField(
            model_name='disbursement',
            name='recipient_is_company',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='disbursement',
            name='recipient_first_name',
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
