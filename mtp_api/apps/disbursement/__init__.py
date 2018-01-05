default_app_config = 'disbursement.app.DisbursementConfig'


class InvalidDisbursementStateException(Exception):

    def __init__(self, conflict_ids, *args, **kwargs):
        self.conflict_ids = conflict_ids
        super().__init__(*args, **kwargs)
