from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('performance', '0002_daily_digital_takeup'),
    ]
    operations = [
        migrations.AddField(
            model_name='digitaltakeup',
            name='amount_by_mtp',
            field=models.IntegerField(null=True, verbose_name='Amount sent digitally'),
        ),
        migrations.AddField(
            model_name='digitaltakeup',
            name='amount_by_post',
            field=models.IntegerField(null=True, verbose_name='Amount by post'),
        ),
    ]
