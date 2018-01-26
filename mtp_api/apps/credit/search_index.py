from elasticsearch_dsl import Boolean, Date, Keyword, Long, Text

from core.search import ModelIndex, registry
from credit.models import Credit


@registry.register
class CreditIndex(ModelIndex):
    model = Credit

    source = Keyword()
    amount = Long()
    resolution = Keyword()
    received_at = Date()
    credited = Boolean()

    sender_name = Text()

    prisoner_name = Text()
    prisoner_number = Keyword()
    prison = Keyword()
    prison_name = Text()

    class Meta:
        index = 'credit'

    @classmethod
    def serialise(cls, instance: Credit):
        data = super().serialise(instance)
        if data['prison']:
            data['prison_name'] = data['prison'].name
            data['prison'] = data['prison'].nomis_id
        return data
