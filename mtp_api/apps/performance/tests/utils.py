import datetime
import random

from credit.constants import LogAction
from credit.models import Log
from performance.models import DigitalTakeup
from prison.models import Prison


def latest_takeup_date():
    date = min(datetime.date.today() - datetime.timedelta(days=1),
               Log.objects.filter(action=LogAction.credited).latest('created').created.date())
    if date.weekday() > 4:
        date -= datetime.timedelta(days=date.weekday() - 4)
    return date


def date_generator(days_of_history):
    date = latest_takeup_date()
    for _ in range(days_of_history):
        if date.weekday() < 5:
            yield date
        date -= datetime.timedelta(days=1)


def generate_digital_takeup(days_of_history=7, typical_takeup=0.7):
    date_range = list(date_generator(days_of_history))
    DigitalTakeup.objects.filter(date__range=(date_range[-1], date_range[0])).delete()
    prisons = list(Prison.objects.all())
    credited_logs = Log.objects.filter(action=LogAction.credited)

    def random_takeup(credits_by_mtp):
        credits_by_post = int(credits_by_mtp * (0.5 - typical_takeup + random.random()))
        return {
            'credits_by_mtp': credits_by_mtp,
            'credits_by_post': credits_by_post,
            'amount_by_mtp': credits_by_mtp * (3000 + random.randrange(-1000, 1000)),
            'amount_by_post': credits_by_post * (3000 + random.randrange(-1000, 1000)),
        }

    for date in date_range:
        credited_on_date = credited_logs.filter(created__date=date)
        DigitalTakeup.objects.bulk_create([
            DigitalTakeup(date=date, prison=prison,
                          **random_takeup(credited_on_date.filter(credit__prison=prison).count()))
            for prison in prisons
        ])
