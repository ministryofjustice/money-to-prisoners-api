from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('disbursement', '0010_comment_category'),
    ]
    operations = [
        migrations.AlterModelOptions(
            name='disbursement',
            options={'get_latest_by': 'created', 'ordering': ('id',), 'permissions': (('view_disbursement', 'Can view disbursements'),)},
        ),
    ]
