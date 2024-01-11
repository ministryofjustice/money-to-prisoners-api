#!/usr/bin/env python
if __name__ == '__main__':
    import os
    import sys

    if sys.version_info[0:2] < (3, 10):
        raise SystemExit('Python 3.10+ is required')

    root_path = os.path.abspath(os.path.dirname(__file__))

    try:
        import mtp_common

        # NB: this version does not need to be updated unless mtp_common changes significantly
        if mtp_common.VERSION < (16,):
            raise ImportError
    except ImportError:
        import importlib.metadata

        (entry_point,) = importlib.metadata.entry_points(name='pip', group='console_scripts')
        pip = entry_point.load()

        print('Pre-installing MTP-common and base requirements')
        pip(['install', '--requirement', f'{root_path}/requirements/base.txt'])

    from mtp_common.build_tasks.executor import Executor
    import mtp_api.apps.core.build_tasks  # noqa

    exit(Executor(root_path=root_path).run())
