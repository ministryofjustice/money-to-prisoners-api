import textwrap

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError

from security.models import SavedSearch, PrisonerProfile, BankAccount, DebitCardSenderDetails

User = get_user_model()


class Command(BaseCommand):
    """
    Removes a user's monitored entities and deletes their saved searches
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('username')
        # TODO: add an option to move monitoring to a different user? requires deduplication

    def handle(self, username, **options):
        try:
            user = User.objects.get_by_natural_key(username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" not found')
        self.stdout.write(f'Removing items monitored by {user.username} ({user.email})')

        self.delete(SavedSearch, 'saved searches', user)
        self.delete(PrisonerProfile.monitoring_users.through, 'monitored prisoners', user)
        self.delete(BankAccount.monitoring_users.through, 'monitored bank account senders', user)
        self.delete(DebitCardSenderDetails.monitoring_users.through, 'monitored debit card senders', user)

    def delete(self, model, description, user):
        self.stdout.write(f'Deleting all {description}…')
        count, deleted_models = model.objects.filter(user=user).delete()
        if count:
            for model, count in deleted_models.items():
                self.stdout.write(f'Deleted {count} × {model}')
        else:
            self.stdout.write(f'No {description} to delete')
