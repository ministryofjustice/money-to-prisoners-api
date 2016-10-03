"""
Docker settings
"""
from .base import *  # noqa
from .base import ENVIRONMENT, os

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG') == 'True'

ALLOWED_HOSTS = [
    'localhost',
    '.dsd.io',
    '.service.gov.uk'
]

# security tightening
if ENVIRONMENT != 'local':
    SECURE_SSL_REDIRECT = True  # also done at nginx level
    # strict-transport set at nginx level
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
