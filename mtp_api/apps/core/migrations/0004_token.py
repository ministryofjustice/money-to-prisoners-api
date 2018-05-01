from django.db import migrations, models
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_auto_20180404_1515'),
    ]
    operations = [
        migrations.CreateModel(
            name='Token',
            fields=[
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('token', models.TextField()),
                ('expires', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ('name',),
                'permissions': (('view_token', 'Can view token'),),
            },
        ),
    ]
