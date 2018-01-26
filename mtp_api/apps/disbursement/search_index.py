from elasticsearch_dsl import Boolean, Date, Keyword, Long, Text

from core.search import ModelIndex, registry
from disbursement.models import Disbursement, DISBURSEMENT_RESOLUTION


@registry.register
class DisbursementIndex(ModelIndex):
    model = Disbursement

    method = Keyword()
    amount = Long()
    resolution = Keyword()
    created_at = Date()
    sent = Boolean()

    prisoner_name = Text()
    prisoner_number = Keyword()
    prison = Keyword()
    prison_name = Text()

    recipient_name = Text()
    recipient_email = Text()

    class Meta:
        index = 'disbursement'

    @classmethod
    def serialise(cls, instance: Disbursement):
        data = super().serialise(instance)
        data['created_at'] = instance.created
        if data['prison']:
            data['prison_name'] = data['prison'].name
            data['prison'] = data['prison'].nomis_id
        data['sent'] = instance.resolution == DISBURSEMENT_RESOLUTION.SENT
        return data
