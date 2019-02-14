from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('prison', '0016_auto_20171121_1110'),
    ]
    operations = [
        migrations.CreateModel(
            name='PrisonBankAccount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address_line1', models.CharField(max_length=250)),
                ('address_line2', models.CharField(blank=True, max_length=250)),
                ('city', models.CharField(max_length=250)),
                ('postcode', models.CharField(max_length=250)),
                ('sort_code', models.CharField(max_length=50)),
                ('account_number', models.CharField(max_length=50)),
                ('remittance_email', models.EmailField(max_length=254)),
            ],
            options={
                'ordering': ('prison',),
            },
        ),
        migrations.AddField(
            model_name='prison',
            name='cms_establishment_code',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='prison',
            name='private_estate',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='prisonbankaccount',
            name='prison',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='prison.Prison'),
        ),
    ]
