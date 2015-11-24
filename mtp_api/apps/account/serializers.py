from rest_framework import serializers

from .models import Batch


class BatchSerializer(serializers.ModelSerializer):

    def validate(self, data):
        label_batch_set = Batch.objects.filter(label=data['label'])
        queryset = Batch.objects.none()
        for transaction in data['transactions']:
            queryset = queryset | label_batch_set.filter(
                transactions=transaction)
        if queryset.exists():
            raise serializers.ValidationError(
                "Some transactions have already been used in a %s batch"
                % data['label'])
        return data

    def create(self, validated_data):
        user = self.context['request'].user

        transactions = validated_data.pop('transactions')
        batch = Batch.objects.create(user=user, **validated_data)
        for transaction in transactions:
            batch.transactions.add(transaction)
        return batch

    class Meta:
        model = Batch
