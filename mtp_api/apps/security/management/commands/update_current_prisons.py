from django.core.management import BaseCommand

from security.models import PrisonerProfile


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        PrisonerProfile.objects.update_current_prisons()
