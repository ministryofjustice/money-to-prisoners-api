import django
from mtp_common.spooling import autodiscover_tasks

django.setup()
autodiscover_tasks()
