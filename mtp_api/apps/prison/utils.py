import logging
from typing import Optional

import requests
from mtp_common import nomis

from prison.models import Prison, PrisonerLocation

logger = logging.getLogger('mtp')


def fetch_prisoner_location_from_nomis(prisoner_location: PrisonerLocation) -> Optional[PrisonerLocation]:
    try:
        new_location = nomis.get_location(prisoner_location.prisoner_number)
        if not new_location:
            logger.error(
                'Malformed response from nomis when looking up prisoner location for '
                f'{prisoner_location.prisoner_number}'
            )
            return None
        new_prison = Prison.objects.get(nomis_id=new_location['nomis_id'])
    except requests.RequestException:
        logger.error(f'Cannot look up prisoner location for {prisoner_location.prisoner_number} in NOMIS')
        return None
    except Prison.DoesNotExist:
        logger.error(f'Cannot find prison matching {new_location["nomis_id"]} in Prison table')
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
