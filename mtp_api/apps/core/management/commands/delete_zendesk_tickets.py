from datetime import timedelta
import logging

from django.conf import settings
from django.core.management import BaseCommand
from django.utils import timezone
import requests

SEARCH_URL = settings.ZENDESK_BASE_URL + '/api/v2/search.json'
DELETE_URL = settings.ZENDESK_BASE_URL + '/api/v2/tickets/destroy_many.json'

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        auth = (
            '%s/token' % settings.ZENDESK_API_USERNAME,
            settings.ZENDESK_API_TOKEN
        )

        query = 'type:ticket status>=solved group_id:{group_id} updated<{two_weeks}'.format(
            group_id=settings.ZENDESK_GROUP_ID,
            two_weeks=(timezone.now() - timedelta(weeks=2)).strftime('%Y-%m-%d')
        )

        while True:
            run_again = False
            response = requests.get(SEARCH_URL, params={'page': 1, 'query': query},
                                    auth=auth, timeout=15)

            if response.status_code == 200:
                data = response.json()
                num_results = len(data['results'])
                if num_results > 0:
                    ids = ','.join(map(str, [r['id'] for r in data['results']]))
                    requests.delete(DELETE_URL, params={'ids': ids},
                                    auth=auth, timeout=15)
                    run_again = True
            else:
                logger.error('Delete old zendesk tickets failed', {'response_body': response.text})

            if not run_again:
                break
