from django.db import migrations

# Describes the tables created by Django and django-oauth-toolkit rather than by Prisoner Money's own models,
# so that the database schema report and anyone reading the database can tell them apart.
# Prisoner Money's own tables are described using `db_table_comment` on their models.
FRAMEWORK_TABLE_COMMENTS = {
    'auth_group': 'Django built-in: groups of permissions. Prisoner Money uses these as the roles given to staff.',
    'auth_group_permissions': 'Django built-in: the permissions in each group.',
    'auth_permission': 'Django built-in: every permission that can be given to a group or user.',
    'auth_user': "Django built-in: accounts for staff who sign in to Prisoner Money apps, and for the apps' own "
                 'service accounts.',
    'auth_user_groups': 'Django built-in: the groups each user belongs to.',
    'auth_user_user_permissions': 'Django built-in: permissions given to a user directly rather than through a group.',
    'django_admin_log': 'Django built-in: changes made through the API admin site, and some user account changes '
                        'made in the apps.',
    'django_content_type': 'Django built-in: a list of every model, referred to by permissions and the admin log.',
    'django_migrations': 'Django built-in: which database migrations have been applied.',
    'django_session': 'Django built-in: sign-in sessions for the API admin site.',
    'oauth2_provider_application': 'Library (django-oauth-toolkit): the Prisoner Money apps that are allowed to sign '
                                   'users in to the API.',
    'oauth2_provider_accesstoken': 'Library (django-oauth-toolkit): tokens issued when a user signs in to an app, '
                                   'which the app uses to call the API.',
    'oauth2_provider_refreshtoken': 'Library (django-oauth-toolkit): tokens that let an app renew an access token '
                                    'without the user signing in again.',
    'oauth2_provider_grant': 'Library (django-oauth-toolkit): authorisation codes. Not used by Prisoner Money, whose '
                             'apps sign users in with a username and password.',
    'oauth2_provider_idtoken': 'Library (django-oauth-toolkit): OpenID Connect identity tokens. Not used by '
                               'Prisoner Money, which has OpenID Connect switched off.',
    'oauth2_provider_devicegrant': 'Library (django-oauth-toolkit): sign-in codes for devices without a keyboard. '
                                   'Not used by Prisoner Money.',
}


def quote_literal(value):
    return "'%s'" % value.replace("'", "''")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_delete_token'),
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('oauth2_provider', '0014_alter_help_text'),
        ('sessions', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                f'COMMENT ON TABLE {table} IS {quote_literal(comment)}'
                for table, comment in FRAMEWORK_TABLE_COMMENTS.items()
            ],
            reverse_sql=[
                f'COMMENT ON TABLE {table} IS NULL'
                for table in FRAMEWORK_TABLE_COMMENTS
            ],
        ),
    ]
