from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '__first__'),
        ('mtp_auth', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='prisonusermapping',
            name='prisons',
            field=models.ManyToManyField(to='prison.Prison'),
        ),
    ]
