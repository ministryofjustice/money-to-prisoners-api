from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('performance', '0001_initial')]
    operations = [
        migrations.AlterModelOptions(
            name='digitaltakeup',
            options={'get_latest_by': 'date', 'ordering': ('date',),
                     'verbose_name': 'digital take-up', 'verbose_name_plural': 'digital take-up'},
        ),
        migrations.RenameField(
            model_name='digitaltakeup',
            old_name='start_date',
            new_name='date',
        ),
        migrations.AlterUniqueTogether(
            name='digitaltakeup',
            unique_together={('date', 'prison')},
        ),
        migrations.RemoveField(
            model_name='digitaltakeup',
            name='end_date',
        ),
    ]
