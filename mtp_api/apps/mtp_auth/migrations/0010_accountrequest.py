import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):
    dependencies = [
        ('prison', '0016_auto_20171121_1110'),
        ('mtp_auth', '0009_login'),
    ]
    operations = [
        migrations.CreateModel(
            name='AccountRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('username', models.CharField(max_length=150, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()])),
                ('first_name', models.CharField(max_length=30)),
                ('last_name', models.CharField(max_length=30)),
                ('email', models.EmailField(max_length=254)),
                ('reason', models.TextField(blank=True)),
                ('prison', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='prison.Prison')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='mtp_auth.Role')),
            ],
            options={
                'ordering': ('created',),
            },
        ),
    ]
