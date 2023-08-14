from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0009_auto_20150825_0918'),
    ]

    operations = [
        migrations.AlterField(
            model_name='log',
            name='action',
            field=models.CharField(choices=[('created', 'Created'), ('locked', 'Locked'), ('unlocked', 'Unlocked'), ('credited', 'Credited'), ('uncredited', 'Uncredited')], max_length=50),
        ),
    ]
