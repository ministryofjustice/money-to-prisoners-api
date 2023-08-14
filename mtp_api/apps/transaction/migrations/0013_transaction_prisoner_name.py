from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transaction', '0012_remove_transaction_upload_counter'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='prisoner_name',
            field=models.CharField(max_length=250, null=True, blank=True),
        ),
    ]
