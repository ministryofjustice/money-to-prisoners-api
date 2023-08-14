from django.db import models, migrations
import model_utils.fields
from django.conf import settings
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.OAUTH2_PROVIDER_APPLICATION_MODEL),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mtp_auth', '0002_prisonusermapping_prisons'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApplicationUserMapping',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('application', models.ForeignKey(to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL, on_delete=models.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
