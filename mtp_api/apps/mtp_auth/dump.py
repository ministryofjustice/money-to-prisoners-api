from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from core.dump import Serialiser

User = get_user_model()


class NomsOpsUserSerialiser(Serialiser):
    """
    Serialises users of the Prisoner Money Intelligence website, whether active or not, ignoring super-users.
    """
    record_type = 'noms_ops_users'

    def get_queryset(self):
        return Group.objects.get(name='Security').user_set.filter(is_superuser=False)

    def get_modified_records(self, after, before):
        # NB: the User model does not track modification so all records should be returned
        return self.get_queryset().order_by('pk').iterator(chunk_size=1000)

    def get_headers(self):
        return [
            'Created at',
            'Exported at',
            'Internal ID',
            'Username',
            'First name',
            'Last name',
            'Email',
            'Member of FIU',
            'Status',
            'Last login',
            'URL',
        ]

    def serialise(self, record: User):
        return {
            'Created at': record.date_joined,
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'Username': record.username,
            'First name': record.first_name,
            'Last name': record.last_name,
            'Email': record.email,
            'Member of FIU': str(record.groups.filter(name='FIU').exists()),
            'Status': 'Can log in' if record.is_active else 'Suspended',
            'Last login': record.last_login,
            'URL': f'{settings.NOMS_OPS_URL}/users/{record.username}/edit/',
        }
