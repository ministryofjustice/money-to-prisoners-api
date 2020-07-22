import django.contrib.postgres.fields
from django.db import migrations, models


SPLIT_CHECK_DESCRIPTION = '''
UPDATE security_check
SET description_migration = regexp_split_to_array(trim(description), '\\.\\s*');
'''

JOIN_CHECK_DESCRIPTION = '''
UPDATE security_check
SET description = array_to_string(description_migration, '. ');
'''


class Migration(migrations.Migration):
    dependencies = [
        ('security', '0029_remove_check_description_prefix'),
    ]
    operations = [
        migrations.AddField(
            model_name='check',
            name='description_migration',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=100), blank=True, null=True, size=None),
        ),
        migrations.RunSQL(sql=SPLIT_CHECK_DESCRIPTION, reverse_sql=JOIN_CHECK_DESCRIPTION),
        migrations.RemoveField(
            model_name='check',
            name='description',
        ),
        migrations.RenameField(
            model_name='check',
            old_name='description_migration',
            new_name='description',
        ),
    ]
