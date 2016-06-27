import logging

from django.contrib.auth import get_user_model, user_logged_in
from oauth2_provider.oauth2_validators import OAuth2Validator

from .models import FailedLoginAttempt

logger = logging.getLogger('mtp')


class LockedOut(Exception):
    pass


class ApplicationRequestValidator(OAuth2Validator):
    def validate_user(self, username, password, client, request, *args, **kwargs):
        user = get_user_model().objects.filter(username=username).first()
        try:
            if user and FailedLoginAttempt.objects.is_locked_out(user, client):
                logger.info('User "%s" is locked out' % username)
                raise LockedOut

            valid = super().validate_user(
                username, password, client, request, *args, **kwargs
            )
            if valid:
                FailedLoginAttempt.objects.delete_failed_attempts(user, client)
                user_logged_in.send(sender=user.__class__, request=request, user=user)
                return True
            elif user:
                logger.info('User "%s" failed login' % username)
                FailedLoginAttempt.objects.add_failed_attempt(user, client)
        except LockedOut:
            pass

        request.user = None
        return False
