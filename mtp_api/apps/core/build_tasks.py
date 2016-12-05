from mtp_common.build_tasks.executor import Context
from mtp_common.build_tasks.tasks import tasks


@tasks.register(hidden=True)
def bundle_javascript(context: Context):
    """
    Performs no actions
    """
    rsync_flags = '-avz' if context.verbosity == 2 else '-az'
    context.shell('rsync %s %s %s/' % (rsync_flags, context.app.javascript_source_path, context.app.asset_build_path))


@tasks.register(hidden=True)
def take_screenshots(_: Context):
    """
    Performs no actions
    """
