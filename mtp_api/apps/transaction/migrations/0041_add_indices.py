from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('transaction', '0040_auto_20161214_1603'),
    ]
    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='category',
            field=models.CharField(choices=[('debit', 'Debit'), ('credit', 'Credit')], db_index=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='received_at',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.CharField(choices=[('bank_transfer', 'Bank transfer'), ('administrative', 'Administrative')], db_index=True, max_length=50),
        ),
    ]
