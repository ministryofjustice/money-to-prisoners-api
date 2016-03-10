import logging

from django.test.runner import DiscoverRunner


class TestRunner(DiscoverRunner):
    def run_suite(self, suite, **kwargs):
        if self.verbosity < 2:
            # makes test output quieter because some tests deliberately cause warning messages
            logger = logging.getLogger('mtp')
            logger.setLevel(logging.ERROR)
        return super(TestRunner, self).run_suite(suite, **kwargs)
