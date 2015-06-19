from .base import *


INSTALLED_APPS += (
    'django_jenkins',
)

TEST_RUNNER = 'django_jenkins.runner.CITestSuiteRunner'
