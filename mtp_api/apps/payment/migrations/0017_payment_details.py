from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payment', '0016_simple_indexes'),
    ]
    operations = [
        migrations.AddField(
            model_name='payment',
            name='card_number_first_digits',
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='worldpay_id',
            field=models.CharField(blank=True, db_index=True, max_length=250, null=True),
        ),
    ]
