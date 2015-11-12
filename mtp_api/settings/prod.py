"""
Production/Docker settings
"""
from .base import *

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
SECURE_SSL_REDIRECT = True  # also done at nginx level
SECURE_HSTS_SECONDS = 300
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
