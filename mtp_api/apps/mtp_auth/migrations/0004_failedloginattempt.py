from django.db import models, migrations
from django.conf import settings
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.OAUTH2_PROVIDER_APPLICATION_MODEL),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mtp_auth', '0003_applicationusermapping'),
    ]

    operations = [
        migrations.CreateModel(
            name='FailedLoginAttempt',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('created', model_utils.fields.AutoCreatedField(verbose_name='created', editable=False, default=django.utils.timezone.now)),
                ('modified', model_utils.fields.AutoLastModifiedField(verbose_name='modified', editable=False, default=django.utils.timezone.now)),
                ('application', models.ForeignKey(to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL, on_delete=models.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
            options={
                'abstract': False,
                'ordering': ('-created',)
            },
        ),
    ]
