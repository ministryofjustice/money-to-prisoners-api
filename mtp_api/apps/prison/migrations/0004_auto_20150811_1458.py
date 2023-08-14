from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0003_remove_prisonerlocation_upload_counter'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='prisonerlocation',
            index_together=set([('prisoner_number', 'prisoner_dob')]),
        ),
    ]
