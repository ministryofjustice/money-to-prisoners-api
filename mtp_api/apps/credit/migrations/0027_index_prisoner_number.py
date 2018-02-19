from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('credit', '0026_auto_20180116_1217'),
    ]
    operations = [
        migrations.AlterField(
            model_name='credit',
            name='prisoner_number',
            field=models.CharField(blank=True, db_index=True, max_length=250, null=True),
        ),
        migrations.AlterField(
            model_name='credit',
            name='single_offender_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
