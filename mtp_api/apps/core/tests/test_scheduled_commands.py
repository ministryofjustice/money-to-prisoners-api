from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

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
        run_commands.handle()

        from prison.models import PrisonerLocation
        self.assertEqual(PrisonerLocation.objects.count(), 60)

        from transaction.models import Transaction
        self.assertEqual(Transaction.objects.count(), 70)
