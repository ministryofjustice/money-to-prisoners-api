from opencensus.ext.azure.log_exporter import AzureLogHandler

from mtp_api.settings import callback_add_role_name


class AppLogger(AzureLogHandler):
    def __init__(self, **options):
        super().__init__(**options)
        super().add_telemetry_processor(callback_add_role_name)
