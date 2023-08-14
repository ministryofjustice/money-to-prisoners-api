from django.db import models, migrations
import model_utils.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Prison',
            fields=[
                ('created', model_utils.fields.AutoCreatedField(editable=False, verbose_name='created', default=django.utils.timezone.now)),
                ('modified', model_utils.fields.AutoLastModifiedField(editable=False, verbose_name='modified', default=django.utils.timezone.now)),
                ('nomis_id', models.CharField(serialize=False, max_length=3, primary_key=True, verbose_name='NOMIS id')),
                ('name', models.CharField(max_length=500)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
