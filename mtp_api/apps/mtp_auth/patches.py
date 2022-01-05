import json

from oauth2_provider.views import TokenView


class ModifiedTokenView(TokenView):
    """
    Patches responses to be like those returned by `oauthlib` prior to version 3.
    Previously, a 401 was returned when invalid credentials were used with
    the Resource Owner Password Credentials Grant flow.
    See https://github.com/oauthlib/oauthlib/issues/264 and https://github.com/oauthlib/oauthlib/issues/619
    Versions 3+ return 400 making it tougher to distinguish between incorrect passwords and other errors.
    This patch reverts the status code back to 401, but only in the case where credentials were incorrect.
    """
    # Sample of a true 400 response:
    # {"error": "unsupported_grant_type"}
    # Sample of a true 403 response (e.g. when request and credentials are valid, but client does not match):
    # {"error": "restricted_client"}
    # Sample of a response that will be reverted to 401
    # {"error": "invalid_grant", "error_description": "Invalid credentials given."}
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 400:
            response_content = json.loads(response.content)
            error = response_content.get('error')
            error_description = response_content.get('error_description') or ''
            if error == 'invalid_grant' and 'Invalid credentials given' in error_description:
                response.status_code = 401
        return response


def patch_oauth2_provider_token_view():
    import oauth2_provider.views

    oauth2_provider.views.TokenView = ModifiedTokenView
