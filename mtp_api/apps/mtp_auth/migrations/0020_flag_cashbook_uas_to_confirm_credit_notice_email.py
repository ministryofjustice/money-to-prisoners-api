from django.db import migrations

FLAG_NAME = 'confirm_credit_notice_email'


def add_flag_to_confirm_credit_notice_email(apps, schema_editor):
    user_class = apps.get_model('auth', 'User')
    cashbook_uas = user_class.objects.filter(is_active=True, is_superuser=False) \
        .filter(groups__name='PrisonClerk') \
        .filter(groups__name='UserAdmin') \
        .values_list('pk', flat=True)

    flag_class = apps.get_model('mtp_auth', 'Flag')
    flag_class.objects.bulk_create([
        flag_class(user_id=user_pk, name=FLAG_NAME)
        for user_pk in cashbook_uas
    ])


def remove_flags_to_confirm_credit_notice_email(apps, schema_editor):
    flag_class = apps.get_model('mtp_auth', 'Flag')
    flag_class.object.filter(name=FLAG_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('mtp_auth', '0019_Remove_UserAdmin_Group_from_Security_if_not_FIU'),
    ]
    operations = [
        migrations.RunPython(
            add_flag_to_confirm_credit_notice_email,
            reverse_code=remove_flags_to_confirm_credit_notice_email,
        ),
    ]
