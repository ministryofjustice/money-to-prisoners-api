import os
import shlex

from django.core.management import call_command
from mtp_common.build_tasks import tasks as mtp_common_tasks
from mtp_common.build_tasks.executor import Context
from mtp_common.build_tasks.tasks import serve, tasks

serve.dependencies += ('migrate',)


@tasks.register('build', 'migrate')
def start(context: Context, port=8000, test_mode=False):
    """
    Starts a development server with test data
    """
    if not test_mode:
        super_task = context.overidden_tasks[0]
        return super_task(context=context, port=port)
    context.setup_django()
    return call_command('testserver', 'initial_groups', 'test_prisons', addrport='0:%s' % port, interactive=False)


@tasks.register('python_dependencies')
def migrate(context: Context):
    """
    Migrates the database models
    Use `./manage.py migrate` for fine-grained options
    """
    context.management_command('migrate', interactive=False)


@tasks.register('migrate')
def schema_report(context: Context, output_path='schema-spy-report'):
    """
    Generates a SchemaSpy report of the database structure; needs Docker
    Matches the report published by money-to-prisoners-deploy
    """
    context.setup_django()
    from django.conf import settings

    database = settings.DATABASES['default']
    host = database['HOST']
    if host in ('', 'localhost', '127.0.0.1'):
        # SchemaSpy runs in a container, so reach the database through the docker host
        host = 'host.docker.internal'
    output_path = os.path.abspath(output_path)
    os.makedirs(output_path, exist_ok=True)
    args = [
        '--rm', '--add-host=host.docker.internal:host-gateway',
        '--user', f'{os.getuid()}:{os.getgid()}',
        '--volume', f'{output_path}:/output',
        # NB: keep in step with the version used by money-to-prisoners-deploy's schema-spy workflow
        'schemaspy/schemaspy:6.2.4',
        '-t', 'pgsql11', '-host', host, '-port', database['PORT'] or '5432',
        '-db', database['NAME'], '-s', 'public', '-u', database['USER'], '-vizjs',
    ]
    if database['PASSWORD']:
        args += ['-p', database['PASSWORD']]
    context.shell('docker run', *map(shlex.quote, args))
    context.info(f'Report written to {output_path}/index.html')


@tasks.register(hidden=True)
def bundle_javascript(context: Context):
    """
    Copies javascript sources
    No compilation is necessary
    """
    rsync_flags = '-avz' if context.verbosity == 2 else '-az'
    context.shell('rsync %s %s %s/' % (rsync_flags, context.app.javascript_source_path, context.app.asset_build_path))


mtp_common_tasks.bundle_javascript = bundle_javascript


@tasks.register(hidden=True)
def take_screenshots(_: Context):
    """
    Performs no actions
    """
