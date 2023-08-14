from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0004_auto_20150811_1458'),
    ]

    operations = [
        migrations.AddField(
            model_name='prison',
            name='general_ledger_code',
            field=models.CharField(max_length=3, default='000'),
            preserve_default=False,
        ),
    ]
