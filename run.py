#!/usr/bin/env python
if __name__ == '__main__':
    import os
    import sys

    if sys.version_info[0:2] < (3, 4):
        raise SystemExit('python 3.4+ is required')

    try:
        import mtp_common

        if mtp_common.VERSION < (5,):
            raise ImportError
    except ImportError:
        try:
            from pip import main as pip_main
        except ImportError:
            raise SystemExit('setuptools and pip are required')

        print('Pre-installing MTP-common')
        pip_main(['--quiet', 'install', '--upgrade', 'money-to-prisoners-common'])

    from mtp_common.build_tasks.executor import Executor
    import mtp_api.apps.core.build_tasks  # noqa

    exit(Executor(root_path=os.path.dirname(__file__)).run())
