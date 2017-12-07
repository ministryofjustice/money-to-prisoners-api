from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('service', '0004_auto_20171206_1135'),
    ]
    operations = [
        migrations.AlterField(
            model_name='notification',
            name='level',
            field=models.SmallIntegerField(choices=[(20, 'Info'), (25, 'Success'), (30, 'Warning'), (40, 'Error')]),
        ),
    ]
