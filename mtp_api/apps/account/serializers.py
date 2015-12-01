from rest_framework import serializers

from .models import Batch


class BatchSerializer(serializers.ModelSerializer):

    def create(self, validated_data):
        user = self.context['request'].user

        transactions = validated_data.pop('transactions')
        batch = Batch.objects.create(user=user, **validated_data)
        for transaction in transactions:
            batch.transactions.add(transaction)
        return batch

    class Meta:
        model = Batch
