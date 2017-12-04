from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0003_auto_20171128_1528'),
    ]
    operations = [
        migrations.RenameField(
            model_name='recipient',
            old_name='name',
            new_name='first_name',
        ),
        migrations.AddField(
            model_name='recipient',
            name='last_name',
            field=models.CharField(default='', max_length=250),
            preserve_default=False,
        ),
    ]
