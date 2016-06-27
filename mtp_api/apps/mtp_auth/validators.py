import logging

from django.contrib.auth import get_user_model, user_logged_in
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2 import OAuth2Error

from .models import ApplicationUserMapping, FailedLoginAttempt

logger = logging.getLogger('mtp')


class LockedOut(Exception):
    pass


class RestrictedClientError(OAuth2Error):
    """The authenticated user is not authorized to access this client"""
    error = 'restricted_client'
    status_code = 403


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
                if not ApplicationUserMapping.objects.filter(
                        user=request.user, application=client).exists():
                    raise RestrictedClientError(request=request)
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
