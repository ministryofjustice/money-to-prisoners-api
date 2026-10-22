from django.db import migrations

# Describes the columns of the tables created by Django and django-oauth-toolkit, whose tables are described
# in 0006_framework_table_comments. Prisoner Money's own columns are described using `db_comment` on their models.
FRAMEWORK_COLUMN_COMMENTS = {
    'auth_group': {
        'name': 'Name of the group, such as PrisonClerk or Security.',
    },
    'auth_group_permissions': {
        'group_id': 'The group.',
        'permission_id': 'A permission in the group.',
    },
    'auth_permission': {
        'name': 'Description of the permission, such as Can view credit.',
        'content_type_id': 'The model that the permission applies to.',
        'codename': 'Short code for the permission, such as view_credit.',
    },
    'auth_user': {
        'password': 'The password, stored as a one-way hash so it cannot be read back.',
        'last_login': 'When the user last signed in.',
        'is_superuser': 'Whether the user has every permission without being given them.',
        'username': 'Username used to sign in. Not case-sensitive.',
        'first_name': 'First name.',
        'last_name': 'Last name.',
        'email': 'Email address.',
        'is_staff': 'Whether the user may sign in to the API admin site.',
        'is_active': 'Whether the user may sign in. Accounts are made inactive after a long time without signing in.',
        'date_joined': 'When the account was created.',
    },
    'auth_user_groups': {
        'user_id': 'The user.',
        'group_id': 'A group the user belongs to.',
    },
    'auth_user_user_permissions': {
        'user_id': 'The user.',
        'permission_id': 'A permission given to the user directly.',
    },
    'django_admin_log': {
        'action_time': 'When the change was made.',
        'object_id': 'ID of the row that was changed.',
        'object_repr': 'Short description of the row that was changed, as it was at the time.',
        'action_flag': 'What was done: 1 added, 2 changed, 3 deleted.',
        'change_message': 'Details of what was changed.',
        'content_type_id': 'The model of the row that was changed.',
        'user_id': 'Who made the change.',
    },
    'django_content_type': {
        'app_label': 'The app the model belongs to, such as credit.',
        'model': 'Name of the model, in lower case, such as credit.',
    },
    'django_migrations': {
        'app': 'The app the migration belongs to.',
        'name': 'Name of the migration.',
        'applied': 'When the migration was applied.',
    },
    'django_session': {
        'session_key': 'Identifies the session. Sent to the browser in a cookie.',
        'session_data': 'Data kept for the session, encoded and signed.',
        'expire_date': 'When the session expires.',
    },
    'oauth2_provider_accesstoken': {
        'token': 'The access token.',
        'token_checksum': 'Checksum of the token, used to look it up.',
        'expires': 'When the token expires.',
        'scope': 'What the token allows the app to do.',
        'application_id': 'The app the token was issued to.',
        'user_id': 'The user the token was issued for.',
        'created': 'When this row was created.',
        'updated': 'When this row was last changed.',
        'source_refresh_token_id': 'The refresh token used to issue this token, if any.',
        'id_token_id': 'The OpenID Connect identity token issued with this token. Not used.',
    },
    'oauth2_provider_application': {
        'client_id': 'Identifies the app when it signs users in.',
        'redirect_uris': 'Addresses the user may be sent back to after signing in. Not used.',
        'post_logout_redirect_uris': 'Addresses the user may be sent back to after signing out. Not used.',
        'allowed_origins': 'Websites allowed to call the token endpoint from a browser. Not used.',
        'client_type': 'Whether the app can keep a secret: confidential or public.',
        'authorization_grant_type': 'How the app signs users in; Prisoner Money apps use password.',
        'client_secret': 'Secret the app uses to identify itself, stored as a one-way hash if hash_client_secret '
                         'is set.',
        'hash_client_secret': 'Whether client_secret is stored as a one-way hash.',
        'name': 'Name of the app, such as Cashbook.',
        'user_id': 'Who registered the app. Not used.',
        'skip_authorization': 'Whether users are not asked to approve the app. Not used.',
        'created': 'When this row was created.',
        'updated': 'When this row was last changed.',
        'algorithm': 'Signing method for OpenID Connect identity tokens. Not used.',
    },
    'oauth2_provider_refreshtoken': {
        'token': 'The refresh token.',
        'access_token_id': 'The access token this token can renew.',
        'application_id': 'The app the token was issued to.',
        'user_id': 'The user the token was issued for.',
        'created': 'When this row was created.',
        'updated': 'When this row was last changed.',
        'revoked': 'When the token was used or cancelled; empty while it can still be used.',
        'token_family': 'Links the refresh tokens issued one after another in the same sign-in.',
    },
    'oauth2_provider_grant': {
        'code': 'The authorisation code.',
        'expires': 'When the code expires.',
        'redirect_uri': 'Address the user is sent back to with the code.',
        'scope': 'What the code allows the app to do.',
        'application_id': 'The app the code was issued to.',
        'user_id': 'The user the code was issued for.',
        'created': 'When this row was created.',
        'updated': 'When this row was last changed.',
        'code_challenge': 'Value the app must match to use the code.',
        'code_challenge_method': 'How code_challenge was made.',
        'nonce': 'Value passed on to the OpenID Connect identity token.',
        'claims': 'OpenID Connect details requested.',
    },
    'oauth2_provider_idtoken': {
        'jti': 'Identifies the token.',
        'expires': 'When the token expires.',
        'scope': 'What the token covers.',
        'created': 'When this row was created.',
        'updated': 'When this row was last changed.',
        'application_id': 'The app the token was issued to.',
        'user_id': 'The user the token was issued for.',
    },
    'oauth2_provider_devicegrant': {
        'device_code': 'Code held by the device.',
        'user_code': 'Code the user types in to approve the device.',
        'scope': 'What the grant allows the device to do.',
        'interval': 'Seconds the device must wait between checks.',
        'expires': 'When the codes expire.',
        'status': 'Whether the user has approved the device.',
        'client_id': 'The app the device belongs to.',
        'last_checked': 'When the device last checked for approval.',
        'user_id': 'The user who approved the device.',
    },
}


def quote_literal(value):
    return "'%s'" % value.replace("'", "''")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_add_db_comments'),
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('oauth2_provider', '0014_alter_help_text'),
        ('sessions', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                f'COMMENT ON COLUMN {table}.{column} IS {quote_literal(comment)}'
                for table, columns in FRAMEWORK_COLUMN_COMMENTS.items()
                for column, comment in columns.items()
            ],
            reverse_sql=[
                f'COMMENT ON COLUMN {table}.{column} IS NULL'
                for table, columns in FRAMEWORK_COLUMN_COMMENTS.items()
                for column in columns
            ],
        ),
    ]
