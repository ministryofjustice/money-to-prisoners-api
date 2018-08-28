from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mtp_auth', '0011_remove_role_managed_roles'),
    ]
    operations = [
        migrations.CreateModel(
            name='Flag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.SlugField()),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='flags', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='flag',
            unique_together={('user', 'name')},
        ),
    ]
