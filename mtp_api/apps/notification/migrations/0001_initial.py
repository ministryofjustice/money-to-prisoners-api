from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import notification.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('credit', '0032_merge_20190218_1205'),
        ('disbursement', '0019_auto_20181106_1641'),
        ('security', '0024_migrate_saved_searches'),
    ]
    operations = [
        migrations.CreateModel(
            name='CreditEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('credit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='credit.Credit')),
            ],
        ),
        migrations.CreateModel(
            name='DisbursementEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('disbursement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='disbursement.Disbursement')),
            ],
        ),
        migrations.CreateModel(
            name='EmailNotificationPreferences',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('frequency', models.CharField(choices=[('never', 'Never'), ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], max_length=50)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule', models.CharField(max_length=8, validators=[notification.models.validate_rule_code])),
                ('description', models.CharField(blank=True, max_length=500)),
                ('triggered_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'permissions': (('view_event', 'Can view event'),),
            },
        ),
        migrations.CreateModel(
            name='PrisonerProfileEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='prisoner_profile_event', to='notification.Event')),
                ('prisoner_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='security.PrisonerProfile')),
            ],
        ),
        migrations.CreateModel(
            name='RecipientProfileEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='recipient_profile_event', to='notification.Event')),
                ('recipient_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='security.RecipientProfile')),
            ],
        ),
        migrations.CreateModel(
            name='SenderProfileEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='sender_profile_event', to='notification.Event')),
                ('sender_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='security.SenderProfile')),
            ],
        ),
        migrations.AddField(
            model_name='disbursementevent',
            name='event',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='disbursement_event', to='notification.Event'),
        ),
        migrations.AddField(
            model_name='creditevent',
            name='event',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='credit_event', to='notification.Event'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['-triggered_at', 'id'], name='notificatio_trigger_ccb935_idx'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['rule'], name='notificatio_rule_0b334e_idx'),
        ),
    ]
