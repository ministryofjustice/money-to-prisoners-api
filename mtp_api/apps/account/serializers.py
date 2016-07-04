from rest_framework import serializers

from .models import Batch, Balance


class BatchSerializer(serializers.ModelSerializer):

    def create(self, validated_data):
        user = self.context['request'].user

        transactions = validated_data.pop('transactions')
        batch = Batch.objects.create(user=user, **validated_data)
        batch.transactions.add(*transactions)
        return batch

    def update(self, instance, validated_data):
        transactions = validated_data.pop('transactions')
        instance.transactions.add(*transactions)
        return super().update(instance, validated_data)

    class Meta:
        model = Batch
        fields = '__all__'


class BalanceSerializer(serializers.ModelSerializer):

    def validate(self, data):
        previous_balance = Balance.objects.filter(date=data['date'])
        if previous_balance.exists():
            raise serializers.ValidationError('Balance exists for date %s' %
                                              data['date'])
        return data

    class Meta:
        model = Balance
        fields = '__all__'
