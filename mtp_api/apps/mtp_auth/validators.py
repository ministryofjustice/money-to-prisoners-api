import logging

from django.contrib.auth import get_user_model
from oauth2_provider.oauth2_validators import OAuth2Validator

from .models import ApplicationUserMapping, FailedLoginAttempt

logger = logging.getLogger()


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
            if valid and ApplicationUserMapping.objects.filter(
                    user=request.user, application=client).exists():
                FailedLoginAttempt.objects.delete_failed_attempts(user, client)
                return True
            elif user:
                logger.info('User "%s" failed login' % username)
                FailedLoginAttempt.objects.add_failed_attempt(user, client)
        except LockedOut:
            pass

        request.user = None
        return False
