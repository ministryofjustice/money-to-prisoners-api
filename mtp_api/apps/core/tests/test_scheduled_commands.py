import logging
from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import captured_stdout
from django.utils import timezone
from mtp_common.test_utils import silence_logger

from core.models import ScheduledCommand
from core.management.commands import run_scheduled_commands


class ScheduledCommandsTestCase(TestCase):
    def test_command_validation_fails(self):
        try:
            command = ScheduledCommand(
                name='non_existent_command', arg_string='', cron_entry='* * * * *'
            )
            command.clean_fields()
            self.fail('No ValidationError raised by invalid command')
        except ValidationError:
            pass

    def test_command_validation(self):
        command = ScheduledCommand(
            name='load_test_data', arg_string='', cron_entry='* * * * *'
        )
        command.clean_fields()

    def test_cron_entry_validation_fails(self):
        try:
            command = ScheduledCommand(
                name='load-test_data', arg_string='', cron_entry='* F F * *'
            )
            command.clean_fields()
            self.fail('No ValidationError raised by invalid cron entry')
        except ValidationError:
            pass

    def test_newly_created_command_is_scheduled(self):
        command = ScheduledCommand(
            name='load_test_data', arg_string='', cron_entry='* * * * *'
        )
        command.save()
        self.assertTrue(timezone.now() - command.next_execution < timedelta(minutes=1))

    def test_due_command_is_scheduled(self):
        command = ScheduledCommand(
            name='load_test_data',
            arg_string='',
            cron_entry='*/10 * * * *',
            next_execution=timezone.now()
        )
        command.save()
        self.assertTrue(command.is_scheduled())

    def test_not_due_command_is_not_scheduled(self):
        command = ScheduledCommand(
            name='load_test_data',
            arg_string='',
            cron_entry='*/10 * * * *',
            next_execution=timezone.now() + timedelta(minutes=5)
        )
        command.save()
        self.assertFalse(command.is_scheduled())

    def test_command_running(self):
        command = ScheduledCommand(
            name='load_test_data',
            arg_string='--number-of-prisoners 60 --number-of-transactions 70',
            cron_entry='* * * * *',
            next_execution=timezone.now()
        )
        command.save()
        run_commands = run_scheduled_commands.Command()
        with captured_stdout() as stdout, silence_logger(level=logging.ERROR):
            run_commands.handle()

        stdout = stdout.getvalue()
        self.assertIn('Making test users', stdout)
        self.assertIn('random credits', stdout)

        from prison.models import PrisonerLocation
        self.assertEqual(PrisonerLocation.objects.count(), 60)

        from transaction.models import Transaction
        self.assertEqual(Transaction.objects.count(), 70)

    def test_command_deleted_when_flag_set(self):
        command = ScheduledCommand(
            name='load_test_data',
            arg_string='--number-of-prisoners 60 --number-of-transactions 70',
            cron_entry='* * * * *',
            next_execution=timezone.now(),
            delete_after_next=True
        )
        command.save()
        run_commands = run_scheduled_commands.Command()
        with captured_stdout(), silence_logger(level=logging.ERROR):
            run_commands.handle()
        self.assertEqual(ScheduledCommand.objects.all().count(), 0)


def make_due_command():
    return ScheduledCommand.objects.create(
        name='update_security_profiles',
        arg_string='',
        cron_entry='*/30 * * * *',
        next_execution=timezone.now() - timedelta(seconds=1),
    )


def try_advisory_lock(db_connection, command):
    with db_connection.cursor() as cursor:
        cursor.execute(
            'SELECT pg_try_advisory_lock(%s, %s)',
            [run_scheduled_commands.ADVISORY_LOCK_NAMESPACE, command.pk],
        )
        return cursor.fetchone()[0]


class ScheduledCommandLockingTestCase(TestCase):
    def setUp(self):
        super().setUp()
        # a separate database session, as if another api instance
        self.other_connection = connection.copy()

    def tearDown(self):
        self.other_connection.close()
        super().tearDown()

    @mock.patch('core.models.call_command')
    def test_command_not_run_while_another_instance_is_running_it(self, mocked_call_command):
        command = make_due_command()
        next_execution = command.next_execution
        self.assertTrue(try_advisory_lock(self.other_connection, command))

        run_scheduled_commands.Command().handle()
        mocked_call_command.assert_not_called()
        command.refresh_from_db()
        self.assertEqual(command.next_execution, next_execution)

        with self.other_connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock_all()')
        run_scheduled_commands.Command().handle()
        mocked_call_command.assert_called_once_with('update_security_profiles')

    @mock.patch('core.models.call_command')
    def test_lock_released_after_command_runs(self, mocked_call_command):
        command = make_due_command()
        run_scheduled_commands.Command().handle()
        mocked_call_command.assert_called_once()
        self.assertTrue(try_advisory_lock(self.other_connection, command))

    @mock.patch('core.models.call_command', side_effect=RuntimeError)
    def test_failed_command_waits_for_its_next_scheduled_time(self, _):
        command = make_due_command()
        with silence_logger(level=logging.CRITICAL):
            run_scheduled_commands.Command().handle()
        command.refresh_from_db()
        self.assertFalse(command.is_scheduled())
        self.assertTrue(try_advisory_lock(self.other_connection, command))


class ScheduledCommandTransactionTestCase(TransactionTestCase):
    def test_command_runs_outside_a_transaction_after_its_next_execution_is_saved(self):
        command = make_due_command()
        seen_while_running = {}

        def record_state(*args):
            seen_while_running['in_transaction'] = connection.in_atomic_block
            seen_while_running['scheduled'] = ScheduledCommand.objects.get(pk=command.pk).is_scheduled()

        with mock.patch('core.models.call_command', side_effect=record_state):
            run_scheduled_commands.Command().handle()

        # so the command's own work commits as it goes, and other instances see it as no longer due
        self.assertEqual(seen_while_running, {'in_transaction': False, 'scheduled': False})
