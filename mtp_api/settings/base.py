"""
Django settings for mtp_api project.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

APP = 'api'
ENVIRONMENT = os.environ.get('ENV', 'local')
APP_BUILD_DATE = os.environ.get('APP_BUILD_DATE')
APP_GIT_COMMIT = os.environ.get('APP_GIT_COMMIT')


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
SECRET_KEY = 'CHANGE_ME'
ALLOWED_HOSTS = []

START_PAGE_URL = os.environ.get('START_PAGE_URL', 'https://www.gov.uk/send-prisoner-money')
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000')

# Application definition
INSTALLED_APPS = (
    # django core
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # third-party
    'oauth2_provider',
    'rest_framework',
    'django_filters',

    # MTP api & admin
    'core',
    'prison',
    'transaction',
    'mtp_auth',
    'account',
    'payment',
    'credit',
    'performance',
    'service',

    # django admin
    'django.contrib.admin',

    # common
    'mtp_common',
)
if ENVIRONMENT != 'prod':
    INSTALLED_APPS += ('rest_framework_swagger',)


WSGI_APPLICATION = 'mtp_api.wsgi.application'
ROOT_URLCONF = 'mtp_api.urls'
MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

HEALTHCHECKS = ['moj_irat.healthchecks.database_healthcheck']
AUTODISCOVER_HEALTHCHECKS = True

# security tightening
# some overridden in prod/docker settings where SSL is ensured
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = False


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.environ.get('DB_NAME', 'mtp_api'),
        'USER': os.environ.get('DB_USERNAME', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
    }
}


# Internationalization
LANGUAGE_CODE = 'en-gb'
LANGUAGES = (
    ('en-gb', 'English'),
    ('cy', 'Cymraeg'),
)
LOCALE_PATHS = (os.path.join(BASE_DIR, 'translations'),)
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'assets'),
    os.path.join(BASE_DIR, 'assets-static'),
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates')
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'mtp_common.context_processors.app_environment',
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'core.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'core.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 9,
        }
    },
    {
        'NAME': 'core.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'core.password_validation.NumericPasswordValidator',
    },
]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'mtp',
    }
}

EMAIL_BACKEND = 'django_mailgun.MailgunBackend'
MAILGUN_ACCESS_KEY = os.environ.get('MAILGUN_ACCESS_KEY', '')
MAILGUN_SERVER_NAME = os.environ.get('MAILGUN_SERVER_NAME', '')
MAILGUN_FROM_ADDRESS = os.environ.get('MAILGUN_FROM_ADDRESS', '')

# logging settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s [%(levelname)s] %(message)s',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
        },
        'elk': {
            '()': 'mtp_common.logging.ELKFormatter'
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple' if ENVIRONMENT == 'local' else 'elk',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'root': {
        'level': 'WARNING',
        'handlers': ['console'],
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
        'mtp': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}

TEST_RUNNER = 'mtp_common.test_utils.runner.TestRunner'

# sentry exception handling
if os.environ.get('SENTRY_DSN'):
    INSTALLED_APPS = ('raven.contrib.django.raven_compat',) + INSTALLED_APPS
    RAVEN_CONFIG = {
        'dsn': os.environ['SENTRY_DSN'],
        'release': APP_GIT_COMMIT or 'unknown',
    }
    LOGGING['handlers']['sentry'] = {
        'level': 'ERROR',
        'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler'
    }
    LOGGING['root']['handlers'].append('sentry')
    LOGGING['loggers']['mtp']['handlers'].append('sentry')

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.ext.rest_framework.OAuth2Authentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20
}
REQUEST_PAGE_DAYS = 5

# control the time a session exists for; client apps should use this value as well
SESSION_COOKIE_AGE = 60 * 60  # 1 hour
SESSION_SAVE_EVERY_REQUEST = True

OAUTH2_PROVIDER = {
    'ACCESS_TOKEN_EXPIRE_SECONDS': SESSION_COOKIE_AGE,
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
    },
    'OAUTH2_VALIDATOR_CLASS': 'mtp_auth.validators.ApplicationRequestValidator'
}
OAUTH2_PROVIDER_APPLICATION_MODEL = 'oauth2_provider.Application'
MTP_AUTH_LOCKOUT_COUNT = 5  # 5 times
MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD = 30 * 60  # 30 minutes

RUN_CLEANUP_TASKS = os.environ.get('RUN_CLEANUP_TASKS') == 'True'

REF_CODE_BASE = 900001
CARD_REF_CODE_BASE = 800001

SURVEY_GIZMO_API_KEY = os.environ.get('SURVEY_GIZMO_API_KEY')

PERFORMANCE_PLATFORM_API_URL = os.environ.get('PERFORMANCE_PLATFORM_API_URL', 'http://localhost/')
PERFORMANCE_PLATFORM_API_TOKEN = os.environ.get('PERFORMANCE_PLATFORM_API_TOKEN', 'not_a_token')

ZENDESK_BASE_URL = 'https://ministryofjustice.zendesk.com'
ZENDESK_API_USERNAME = os.environ.get('ZENDESK_API_USERNAME', '')
ZENDESK_API_TOKEN = os.environ.get('ZENDESK_API_TOKEN', '')
ZENDESK_GROUP_ID = 26417927

try:
    from .local import *  # noqa
except ImportError:
    pass
