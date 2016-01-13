from .base import *  # noqa

INSTALLED_APPS += (
    'django_jenkins',
)

TEST_RUNNER = 'django_jenkins.runner.CITestSuiteRunner'
