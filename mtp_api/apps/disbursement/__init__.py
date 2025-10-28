class InvalidDisbursementStateException(Exception):
    def __init__(self, conflict_ids, *args, **kwargs):  # noqa: B042
        self.conflict_ids = conflict_ids
        super().__init__(*args, **kwargs)
