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
