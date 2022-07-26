from opencensus.ext.azure.log_exporter import AzureLogHandler


class AppLogger(AzureLogHandler):
    def __init__(self, **options):
        super().__init__(**options)
        super().add_telemetry_processor(callback_add_role_name)


def callback_add_role_name(envelope):
    """ Callback function for opencensus """
    """ This configures cloud_RoleName """
    envelope.tags['ai.cloud.role'] = 'mtp-api'
    envelope.tags['ai.cloud.roleInstance'] = 'mtp-api'
    return True
