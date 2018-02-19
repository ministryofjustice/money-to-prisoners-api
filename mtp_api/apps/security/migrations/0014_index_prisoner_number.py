from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0013_auto_20170713_1604'),
    ]
    operations = [
        migrations.AlterField(
            model_name='prisonerprofile',
            name='prisoner_number',
            field=models.CharField(db_index=True, max_length=250),
        ),
    ]
