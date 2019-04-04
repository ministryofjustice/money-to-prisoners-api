from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('prison', '0017_prison_private_estate'),
    ]
    operations = [
        migrations.CreateModel(
            name='RemittanceEmail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254)),
                ('prison', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='prison.Prison')),
            ],
            options={
                'ordering': ('prison',),
            },
        ),
        migrations.RemoveField(
            model_name='prisonbankaccount',
            name='remittance_email',
        ),
    ]
