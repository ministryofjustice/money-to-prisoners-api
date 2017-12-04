import json
import os

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand


class Command(BaseCommand):
    """
    Synchronises user group permissions with initial_groups.json fixture
    """
    help = __doc__.strip()

    def handle(self, *args, **options):
        path = os.path.join(apps.get_app_config('mtp_auth').path, 'fixtures', 'initial_groups.json')
        with open(path, 'rt') as f:
            fixture = json.load(f)
        group_permissions = {
            model['fields']['name']: model['fields']['permissions']
            for model in fixture
            if model['model'] == 'auth.group'
        }

        for name, permissions in group_permissions.items():
            permission_names = {}
            for permission in permissions:
                try:
                    permission = Permission.objects.get_by_natural_key(*permission)
                    permission_names[permission.pk] = '-'.join(permission.natural_key())
                except (Permission.DoesNotExist, ContentType.DoesNotExist):
                    self.stderr.write('Permission "%s" is missing, have migrations been run?' % '-'.join(permission))
                    continue
            canonical_permissions = set(permission_names.keys())
            try:
                group = Group.objects.get_by_natural_key(name)
                current_permissions = set(group.permissions.values_list('pk', flat=True))

                missing_permissions = canonical_permissions - current_permissions
                if missing_permissions:
                    self.stderr.write('Group "%s" is missing permissions: %s' % (
                        name,
                        ', '.join(permission_names[permission] for permission in missing_permissions)
                    ))
                    if input('Add permissions? [Y/n]: ').lower() != 'n':
                        self.stdout.write('Adding permissions to group')
                        group.permissions.add(*missing_permissions)

                superfluous_permissions = current_permissions - canonical_permissions
                if superfluous_permissions:
                    self.stderr.write('Group "%s" has unexpected permissions: %s' % (
                        name,
                        ', '.join('-'.join(Permission.objects.get(pk=permission).natural_key())
                                  for permission in superfluous_permissions)
                    ))
                    if input('Remove permissions? [y/N]: ').lower() == 'y':
                        self.stdout.write('Removing permissions from group')
                        group.permissions.remove(*superfluous_permissions)
            except Group.DoesNotExist:
                self.stderr.write('Group "%s" does not exist' % name)
                if input('Create it? [Y/n]: ').lower() != 'n':
                    self.stdout.write('Creating group with permissions')
                    group = Group.objects.create(name=name)
                    group.permissions.set(canonical_permissions)
