from mtp_api.settings.base import *  # noqa
from mtp_api.settings.base import INSTALLED_APPS

INSTALLED_APPS += (
    'django_jenkins',
)

TEST_RUNNER = 'django_jenkins.runner.CITestSuiteRunner'
