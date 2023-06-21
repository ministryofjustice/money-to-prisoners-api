from django.db import models, migrations
from django.conf import settings
import model_utils.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('prison', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrisonerLocation',
            fields=[
                ('id', models.AutoField(serialize=False, auto_created=True, primary_key=True, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(editable=False, default=django.utils.timezone.now, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(editable=False, default=django.utils.timezone.now, verbose_name='modified')),
                ('upload_counter', models.PositiveIntegerField()),
                ('prisoner_number', models.CharField(max_length=250)),
                ('prisoner_dob', models.DateField()),
                ('created_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('prison', models.ForeignKey(to='prison.Prison', on_delete=models.CASCADE)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
