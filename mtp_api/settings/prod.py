""" Production settings

See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/
"""

import os


from mtp_api.settings.base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# TODO: Set your ALLOWED_HOSTS

ALLOWED_HOSTS = []



# TODO: Configure production database
DATABASES = {}


SECRET_KEY = os.environ['SECRET_KEY']

DEBUG = False
TEMPLATE_DEBUG = DEUBG
