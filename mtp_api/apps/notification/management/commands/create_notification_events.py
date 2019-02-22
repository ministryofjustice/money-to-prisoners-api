from django.core.management import BaseCommand

from notification.rules import RULES


class Command(BaseCommand):

    def handle(self, **options):
        for rules in RULES:
            RULES[rule].create_events()
