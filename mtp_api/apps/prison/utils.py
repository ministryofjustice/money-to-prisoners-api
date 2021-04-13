import logging
from typing import Optional

import requests
from mtp_common import nomis

from prison.models import Prison, PrisonerLocation

logger = logging.getLogger('mtp')


def fetch_prisoner_location_from_nomis(prisoner_location: PrisonerLocation) -> Optional[PrisonerLocation]:
    new_location = None
    try:
        new_location = nomis.get_location(prisoner_location.prisoner_number)
        if not new_location:
            logger.error(
                'Malformed response from nomis when looking up prisoner location for prisoner',
                {'prisoner_number': prisoner_location.prisoner_number}
            )
            return None
        new_prison = Prison.objects.get(nomis_id=new_location['nomis_id'])
    except requests.RequestException:
        logger.error(
            'Cannot look up prisoner location for prisoner in NOMIS',
            {'prisoner_number': prisoner_location.prisoner_number}
        )
        return None
    except Prison.DoesNotExist:
        logger.error('Cannot find prison in Prison table', {'nomis_id': new_location['nomis_id']})
        return None
    else:
        logger.info(
            f'Location fetched from nomis of {prisoner_location.prisoner_number} is {new_prison.nomis_id}'
        )
        # This update will only persist in python space. It is NOT committed to the database
        # This is because we should be calling credit_prisons_need_updating on any update to PrisonerLocation and that
        # takes too long to do synchronously off the back of a user-triggered API Request
        prisoner_location.prison = new_prison
        return prisoner_location
