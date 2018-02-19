from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0011_disbursement_natural_ordering'),
    ]
    operations = [
        migrations.AlterField(
            model_name='disbursement',
            name='prisoner_number',
            field=models.CharField(db_index=True, max_length=250),
        ),
    ]
