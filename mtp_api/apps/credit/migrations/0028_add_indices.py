from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('credit', '0027_index_prisoner_number'),
    ]
    operations = [
        migrations.AlterField(
            model_name='credit',
            name='amount',
            field=models.PositiveIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='credit',
            name='received_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='credit',
            name='resolution',
            field=models.CharField(choices=[('initial', 'Initial'), ('pending', 'Pending'), ('manual', 'Requires manual processing'), ('credited', 'Credited'), ('refunded', 'Refunded')], db_index=True, default='pending', max_length=50),
        ),
    ]
