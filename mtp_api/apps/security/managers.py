from django.db import connection, models, transaction


class PrisonProfileManager(models.Manager):

    @transaction.atomic
    def update_current_prisons(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE security_prisonerprofile '
                'SET current_prison_id = pl.prison_id '
                'FROM security_prisonerprofile AS pp '
                'LEFT OUTER JOIN prison_prisonerlocation AS pl '
                'ON pp.prisoner_number = pl.prisoner_number '
                'AND pl.active is True '
                'WHERE security_prisonerprofile.id = pp.id '
            )
