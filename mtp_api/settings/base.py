import os
import sys
from urllib.parse import urljoin

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

APP = 'api'
ENVIRONMENT = os.environ.get('ENV', 'local')
APP_BUILD_DATE = os.environ.get('APP_BUILD_DATE')
APP_BUILD_TAG = os.environ.get('APP_BUILD_TAG')
APP_GIT_COMMIT = os.environ.get('APP_GIT_COMMIT')

TEAM_EMAIL = os.environ.get('TEAM_EMAIL', 'mtp@localhost')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or 'CHANGE_ME'
ALLOWED_HOSTS = ['*']

START_PAGE_URL = os.environ.get('START_PAGE_URL', 'https://www.gov.uk/send-prisoner-money')
API_URL = (
    f'https://{os.environ["PUBLIC_API_HOST"]}'
    if os.environ.get('PUBLIC_API_HOST')
    else 'http://localhost:8000'
)
CASHBOOK_URL = (
    f'https://{os.environ["PUBLIC_CASHBOOK_HOST"]}'
    if os.environ.get('PUBLIC_CASHBOOK_HOST')
    else 'http://localhost:8001'
)
BANK_ADMIN_URL = (
    f'https://{os.environ["PUBLIC_BANK_ADMIN_HOST"]}'
    if os.environ.get('PUBLIC_BANK_ADMIN_HOST')
    else 'http://localhost:8002'
)
NOMS_OPS_URL = (
    f'https://{os.environ["PUBLIC_NOMS_OPS_HOST"]}'
    if os.environ.get('PUBLIC_NOMS_OPS_HOST')
    else 'http://localhost:8003'
)
SEND_MONEY_URL = (
    f'https://{os.environ["PUBLIC_SEND_MONEY_HOST"]}'
    if os.environ.get('PUBLIC_SEND_MONEY_HOST')
    else 'http://localhost:8004'
)
EMAILS_URL = (
    f'https://{os.environ["PUBLIC_EMAILS_HOST"]}'
    if os.environ.get('PUBLIC_EMAILS_HOST')
    else 'http://localhost:8006'
)
SITE_URL = API_URL

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
    'drf_yasg',
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
    'security',
    'disbursement',
    'notification',
    'user_event_log',

    # django admin
    'django.contrib.admin',

    # common
    'mtp_common',
    'mtp_common.metrics',
)


WSGI_APPLICATION = 'mtp_api.wsgi.application'
ROOT_URLCONF = 'mtp_api.urls'
MIDDLEWARE = (
    'mtp_common.metrics.middleware.RequestMetricsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

APPLICATIONINSIGHTS_CONNECTION_STRING = os.environ.get('APPLICATIONINSIGHTS_CONNECTION_STRING')
if APPLICATIONINSIGHTS_CONNECTION_STRING:
    from mtp_common.application_insights import AppInsightsTraceExporter
    from opencensus.trace.samplers import ProbabilitySampler

    # Sends traces to Azure Application Insights
    MIDDLEWARE += ('opencensus.ext.django.middleware.OpencensusMiddleware',)
    OPENCENSUS = {
        'TRACE': {
            'SAMPLER': ProbabilitySampler(rate=0.1 if ENVIRONMENT == 'prod' else 1),
            'EXPORTER': AppInsightsTraceExporter(),
        }
    }

HEALTHCHECKS = ['moj_irat.healthchecks.database_healthcheck']
AUTODISCOVER_HEALTHCHECKS = True

METRICS_USER = os.environ.get('METRICS_USER', 'prom')
METRICS_PASS = os.environ.get('METRICS_PASS', 'prom')

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
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'mtp_api'),
        'USER': os.environ.get('DB_USERNAME', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Internationalization
LANGUAGE_CODE = 'en-gb'
LANGUAGES = (
    ('en-gb', 'English'),
    ('cy', 'Cymraeg'),
)
LOCALE_PATHS = (os.path.join(BASE_DIR, 'translations'),)
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_TZ = True
FORMAT_MODULE_PATH = ['mtp_api.settings.formats']


# Static files (CSS, JavaScript, Images)
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'assets'),
    os.path.join(BASE_DIR, 'assets-static'),
]
PUBLIC_STATIC_URL = urljoin(SEND_MONEY_URL, STATIC_URL)

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

GOVUK_NOTIFY_API_KEY = os.environ.get('GOVUK_NOTIFY_API_KEY', '')
GOVUK_NOTIFY_REPLY_TO_PUBLIC = os.environ.get('GOVUK_NOTIFY_REPLY_TO_PUBLIC', '')
GOVUK_NOTIFY_REPLY_TO_STAFF = os.environ.get('GOVUK_NOTIFY_REPLY_TO_STAFF', '')
GOVUK_NOTIFY_BLOCKED_DOMAINS = set(os.environ.get('GOVUK_NOTIFY_BLOCKED_DOMAINS', '').split())
# install GOV.UK Notify fallback for emails accidentally sent using Django's email functionality:
EMAIL_BACKEND = 'mtp_common.notify.email_backend.NotifyEmailBackend'

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
            '()': 'mtp_common.logging.ELKFormatter',
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
if APPLICATIONINSIGHTS_CONNECTION_STRING:
    # Sends messages from `mtp` logger to Azure Application Insights
    LOGGING['handlers']['azure'] = {
        'level': 'INFO',
        'class': 'mtp_common.application_insights.AppInsightsLogHandler',
    }
    LOGGING['loggers']['mtp']['handlers'].append('azure')
    LOGGING['root']['handlers'].append('azure')

TEST_RUNNER = 'mtp_common.test_utils.runner.TestRunner'

# sentry exception handling
if os.environ.get('SENTRY_DSN'):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        integrations=[DjangoIntegration()],
        environment=ENVIRONMENT,
        release=APP_GIT_COMMIT or 'unknown',
        send_default_pii=DEBUG,
        max_request_body_size='medium' if DEBUG else 'never',
    )

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
}
REQUEST_PAGE_DAYS = 5

# control the time a session exists for; client apps should use this value as well
SESSION_COOKIE_AGE = 60 * 60  # 1 hour
SESSION_SAVE_EVERY_REQUEST = True

LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/admin/'

OAUTH2_PROVIDER = {
    'PKCE_REQUIRED': False,
    'OIDC_ENABLED': False,
    'ACCESS_TOKEN_EXPIRE_SECONDS': SESSION_COOKIE_AGE,
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
    },
    'OAUTH2_VALIDATOR_CLASS': 'mtp_auth.validators.ApplicationRequestValidator',
}
OAUTH2_PROVIDER_APPLICATION_MODEL = 'oauth2_provider.Application'
MTP_AUTH_LOCKOUT_COUNT = 5  # 5 times
MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD = 10 * 60  # 10 minutes, update mtp-common locked_out message if changes

REF_CODE_BASE = 900001
CARD_REF_CODE_BASE = 800001

SURVEY_GIZMO_API_KEY = os.environ.get('SURVEY_GIZMO_API_KEY')

PERFORMANCE_PLATFORM_API_URL = os.environ.get('PERFORMANCE_PLATFORM_API_URL', 'http://localhost/')
PERFORMANCE_PLATFORM_API_TOKENS = {
    'completion-rate': os.environ.get(
        'PERFORMANCE_PLATFORM_API_TOKEN_COMPLETION_RATE', 'not_a_token'
    ),
    'transactions-by-channel-type': os.environ.get(
        'PERFORMANCE_PLATFORM_API_TOKEN_DIGITAL_TAKEUP', 'also_not_a_token'
    ),
}

ZENDESK_BASE_URL = 'https://ministryofjustice.zendesk.com'
ZENDESK_API_USERNAME = os.environ.get('ZENDESK_API_USERNAME', '')
ZENDESK_API_TOKEN = os.environ.get('ZENDESK_API_TOKEN', '')
ZENDESK_GROUP_ID = 26417927

HMPPS_CLIENT_ID = os.environ.get('HMPPS_CLIENT_ID', 'prisoner-money')
HMPPS_CLIENT_SECRET = os.environ.get('HMPPS_CLIENT_SECRET', '')
HMPPS_AUTH_BASE_URL = os.environ.get('HMPPS_AUTH_BASE_URL', '')
HMPPS_PRISON_API_BASE_URL = os.environ.get('HMPPS_PRISON_API_BASE_URL', '')

INVOICE_NUMBER_BASE = 1000000

ANALYTICAL_PLATFORM_BUCKET = os.environ.get('ANALYTICAL_PLATFORM_BUCKET', '')
ANALYTICAL_PLATFORM_BUCKET_PATH = os.environ.get('ANALYTICAL_PLATFORM_BUCKET_PATH', '')

LINKSPACE_PRIVATE_KEY_PATH = os.environ.get('LINKSPACE_PRIVATE_KEY_PATH', '')
LINKSPACE_ENDPOINT = os.environ.get('LINKSPACE_ENDPOINT', '')

SWAGGER_SETTINGS = {
    'USE_SESSION_AUTH': False,
    'SECURITY_DEFINITIONS': {
        'oauth2_provider': {
            'type': 'oauth2',
            'description': 'test',
            'flow': 'password',
            'tokenUrl': urljoin(API_URL, '/oauth2/token/'),
            'authorizationUrl': urljoin(API_URL, '/oauth2/authorize/'),
            'scopes': {
                'read': 'Read scope',
                'write': 'Write scope',
            },
        },
    },
    'SHOW_REQUEST_HEADERS': True,
    'SECURITY': [{
        'password': ['read', 'write'],
    }],
    'REFETCH_SCHEMA_WITH_AUTH': True,
    'OAUTH2_CONFIG': {
        'clientId': os.environ.get('MTP_SWAGGER_CLIENT_ID'),
        'clientSecret': os.environ.get('MTP_SWAGGER_CLIENT_SECRET'),
        'appName': 'Money To Prisoners',
    },
}

try:
    from .local import *  # noqa
except ImportError:
    pass
