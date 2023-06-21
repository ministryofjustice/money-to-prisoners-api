from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0003_manual_20151106'),
    ]

    operations = [
        migrations.AlterField(
            model_name='batch',
            name='label',
            field=models.CharField(max_length=30, db_index=True),
        ),
        migrations.AlterModelOptions(
            name='batch',
            options={'ordering': ('-created',), 'verbose_name_plural': 'batches'},
        ),
    ]
