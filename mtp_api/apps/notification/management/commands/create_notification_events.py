from django.core.management import BaseCommand

from notification.models import Subscription


class Command(BaseCommand):

    def handle(self, **options):
        for subscription in Subscription.objects.all():
            subscription.create_events()
