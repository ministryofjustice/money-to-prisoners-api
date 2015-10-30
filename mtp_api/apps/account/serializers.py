from rest_framework import serializers

from .models import File, FileType, Balance


class FileTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = FileType


class BalanceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Balance
        fields = ('opening_balance', 'closing_balance')


class FileSerializer(serializers.ModelSerializer):
    balance = BalanceSerializer(required=False)

    def validate(self, data):
        file_type_set = File.objects.filter(file_type=data['file_type'])
        queryset = File.objects.none()
        for transaction in data['transactions']:
            queryset = queryset | file_type_set.filter(
                transactions=transaction)
        if queryset.exists():
            raise serializers.ValidationError(
                "Some transactions have already been used in a %s file"
                % data['file_type'])
        return data

    def create(self, validated_data):
        balance_data = validated_data.pop('balance', None)
        transactions = validated_data.pop('transactions')
        file = File.objects.create(**validated_data)
        for transaction in transactions:
            file.transactions.add(transaction)
        if balance_data:
            Balance.objects.create(file=file, **balance_data)
        return file

    class Meta:
        model = File
