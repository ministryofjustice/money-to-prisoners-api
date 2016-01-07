#!/usr/bin/env python
"""
Used by the `testserve` action in /run.sh to load basic testing data
and create a super admin user
"""


def main():
    import argparse
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument('--sleep', type=int, default=6)
    args = parser.parse_args()
    time.sleep(args.sleep)

    print('Starting testserver model creation')
    setup_db()
    setup_django()
    load_test_data()
    create_superuser()
    print('Model creation finished')


def setup_db():
    from mtp_api.settings import DATABASES

    DATABASES['default']['NAME'] = 'test_' + DATABASES['default']['NAME']

    from django.db import connection

    connection.connect()
    assert connection.connection.dsn == 'dbname=test_mtp_api user=postgres', \
        'Database must be running in test mode'


def setup_django():
    import django

    django.setup()


def load_test_data():
    from django.core.management import call_command

    call_command('load_test_data', protect_superusers=True, verbosity=1)


def create_superuser():
    from django.contrib.auth.models import User, Group
    from core.tests.utils import give_superusers_full_access

    try:
        admin_user = User.objects.get(username='admin')
    except User.DoesNotExist:
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@local',
            password='admin',
            first_name='Admin',
            last_name='User',
        )
    for group in Group.objects.all():
        admin_user.groups.add(group)
    give_superusers_full_access()


if __name__ == '__main__':
    main()
