from contextlib import contextmanager
import logging

from django.core.management import BaseCommand
from django.db import DatabaseError, connection, transaction

from core.models import ScheduledCommand

logger = logging.getLogger('mtp')

# first key of the two-key form of postgres advisory locks, the second being the scheduled command's primary key
ADVISORY_LOCK_NAMESPACE = 4805


@contextmanager
def advisory_lock(key):
    """
    Holds a session-level postgres advisory lock, which is not tied to a transaction
    and is released if the connection closes; yields whether it was acquired
    """
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s, %s)', [ADVISORY_LOCK_NAMESPACE, key])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s, %s)', [ADVISORY_LOCK_NAMESPACE, key])


class Command(BaseCommand):
    """
    Runs scheduled commands that are due. Called every minute on every api instance.

    Each command runs outside of any transaction so that its own work commits as it goes:
    running a whole command in one transaction held its row locks until it finished,
    e.g. update_security_profiles blocked card payments from updating security profiles for several minutes.
    An advisory lock instead ensures that only one instance runs a given command at a time.
    """

    def handle(self, *args, **options):
        commands = ScheduledCommand.objects.all()
        for command in commands:
            if command.is_scheduled():
                try:
                    self.run_command(command)
                except DatabaseError:
                    logger.warning('Scheduled command "%s" failed to run due to database error', command)
                except Exception:
                    logger.exception('Scheduled command "%s" failed to run', command)

    def run_command(self, command):
        with advisory_lock(command.pk) as acquired:
            if not acquired:
                # another instance is running this command
                return

            # claim the command by moving next_execution on in a short transaction
            # so that other instances will not see it as scheduled
            with transaction.atomic():
                locked_command = (
                    ScheduledCommand.objects.select_for_update(nowait=True)
                    .filter(pk=command.pk)
                    .first()
                )
                if not locked_command or not locked_command.is_scheduled():
                    return
                locked_command.update_next_execution()
                locked_command.save()

            locked_command.run()
