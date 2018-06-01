from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payment', '0015_auto_20180220_1437'),
    ]
    operations = [
        migrations.AlterField(
            model_name='payment',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True),
        ),
    ]
