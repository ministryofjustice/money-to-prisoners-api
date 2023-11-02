from mtp_auth.patches import patch_oauth2_provider_token_view

patch_oauth2_provider_token_view()

from oauth2_provider import urls as oauth2_provider_urls  # noqa: E402


urlpatterns = oauth2_provider_urls.base_urlpatterns
