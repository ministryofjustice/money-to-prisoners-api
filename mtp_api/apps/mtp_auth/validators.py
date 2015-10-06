from oauth2_provider.oauth2_validators import OAuth2Validator

from .models import ApplicationUserMapping


class ApplicationRequestValidator(OAuth2Validator):

    def validate_user(self, username, password, client, request, *args, **kwargs):
        valid = super(ApplicationRequestValidator, self).validate_user(
            username, password, client, request, *args, **kwargs
        )
        if valid and ApplicationUserMapping.objects.filter(
                user=request.user, application=client).exists():
            return True
        request.user = None
        return False
