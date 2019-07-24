from rest_framework import serializers

from account.models import Balance


class BalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Balance
        fields = '__all__'

    def validate(self, data):
        previous_balance = Balance.objects.filter(date=data['date'])
        if previous_balance.exists():
            raise serializers.ValidationError('Balance exists for date %s' % data['date'])
        return data
