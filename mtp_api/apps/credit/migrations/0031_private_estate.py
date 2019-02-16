from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):
    dependencies = [
        ('prison', '0017_prison_private_estate'),
        ('credit', '0030_auto_20181016_1005'),
    ]
    operations = [
        migrations.CreateModel(
            name='PrivateEstateBatch',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('date', models.DateField()),
                ('prison', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='prison.Prison')),
            ],
            options={
                'verbose_name_plural': 'private estate batches',
                'ordering': ('date',),
                'get_latest_by': 'date',
                'unique_together': {('date', 'prison')},
                'permissions': (('view_privateestatebatch', 'Can view batch'),),
            },
        ),
        migrations.AddField(
            model_name='credit',
            name='private_estate_batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='credit.PrivateEstateBatch'),
        ),
    ]
