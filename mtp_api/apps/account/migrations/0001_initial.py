from django.db import models, migrations
import model_utils.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0015_auto_20151019_1430'),
    ]

    operations = [
        migrations.CreateModel(
            name='Balance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('opening_balance', models.IntegerField()),
                ('closing_balance', models.IntegerField()),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='File',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='FileType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('name', models.CharField(max_length=100)),
            ],
        ),
        migrations.AddField(
            model_name='file',
            name='file_type',
            field=models.ForeignKey(to='account.FileType', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='file',
            name='transactions',
            field=models.ManyToManyField(to='transaction.Transaction'),
        ),
        migrations.AddField(
            model_name='balance',
            name='file',
            field=models.OneToOneField(to='account.File', on_delete=models.CASCADE),
        ),
    ]
