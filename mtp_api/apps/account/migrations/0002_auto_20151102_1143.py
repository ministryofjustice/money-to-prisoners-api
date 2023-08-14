from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='filetype',
            name='id',
        ),
        migrations.AddField(
            model_name='filetype',
            name='description',
            field=models.CharField(null=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='filetype',
            name='name',
            field=models.CharField(primary_key=True, max_length=15, serialize=False),
        ),
    ]
