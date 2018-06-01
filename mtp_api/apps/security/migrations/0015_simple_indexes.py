from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0014_index_prisoner_number'),
    ]
    operations = [
        migrations.AlterField(
            model_name='debitcardsenderdetails',
            name='card_number_last_digits',
            field=models.CharField(blank=True, db_index=True, max_length=4, null=True),
        ),
        migrations.AlterField(
            model_name='debitcardsenderdetails',
            name='postcode',
            field=models.CharField(blank=True, db_index=True, max_length=250, null=True),
        ),
    ]
