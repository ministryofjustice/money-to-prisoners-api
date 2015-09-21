from django.db import transaction

from rest_framework import serializers

from transaction.signals import transaction_prisons_need_updating

from .models import PrisonerLocation, Prison


class PrisonSerializer(serializers.ModelSerializer):

    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'general_ledger_code',
            'name'
        )


class PrisonerLocationListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def create(self, validated_data):
        locations = [
            PrisonerLocation(**item) for item in validated_data
        ]

        # delete all current records and insert new batch
        PrisonerLocation.objects.all().delete()
        objects = PrisonerLocation.objects.bulk_create(locations)

        transaction_prisons_need_updating.send(sender=PrisonerLocation)

        return objects


class PrisonerLocationSerializer(serializers.ModelSerializer):

    class Meta:
        model = PrisonerLocation
        list_serializer_class = PrisonerLocationListSerializer
        fields = (
            'prisoner_number',
            'prisoner_dob',
            'prison',
        )
